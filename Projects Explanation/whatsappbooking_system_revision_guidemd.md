# AI Telegram Booking System: Complete n8n Revision Guide

## Table of Contents
1. [Project Overview & Architecture](#1-project-overview--architecture)
2. [Database Schema & Integrations](#2-database-schema--integrations)
3. [Global State Management (Redis)](#3-global-state-management-redis)
4. [Main Orchestrator Workflow](#4-main-orchestrator-workflow)
5. [LLM Integration & Persona (Clara)](#5-llm-integration--persona-clara)
6. [Booking Spoke Workflow](#6-booking-spoke-workflow)
7. [Reschedule Spoke Workflow](#7-reschedule-spoke-workflow)
8. [Cancellation Spoke Workflow](#8-cancellation-spoke-workflow)
9. [FAQ Spoke Workflow](#9-faq-spoke-workflow)
10. [Error Handling & Self-Healing Mechanisms](#10-error-handling--self-healing-mechanisms)
11. [Example Conversation Flows](#11-example-conversation-flows)

---

## 1. Project Overview & Architecture

The **AI Telegram Booking System** is an intelligent, conversational agent designed to act as a medical clinic receptionist. Built entirely on **n8n** using a Hub-and-Spoke architecture, the system efficiently handles user intents via Telegram and seamlessly integrates with Google Sheets (for availability/doctor schedules), Google Calendar (for event creation), and Redis (for maintaining conversation state).

### Core Components
* **Hub (Main Orchestrator)**: Receives Telegram updates, manages session states, filters invalid payloads, builds context for the LLM, routes intents to the appropriate spoke, and sends final replies back to the user.
* **Spokes (Sub-workflows)**: 
  * `BOOK_SPOKE`: Handles scheduling new appointments.
  * `RESCHEDULE_SPOKE`: Modifies existing appointments dynamically.
  * `CANCEL_SPOKE`: Removes appointments and frees up slots.
  * `FAQ_SPOKE`: Answers standard clinic questions.

### Technology Stack
* **Automation Tool**: n8n
* **Frontend/UI**: Telegram Bot API
* **State Management**: Redis (Session memory)
* **LLM Engine**: Google Gemini 2.5 Flash-lite (Langchain integration)
* **Database/Availability Engine**: Google Sheets
* **Booking Engine**: Google Calendar

---

## 2. Database Schema & Integrations

The system utilizes Google Sheets as a dynamic database. 

### Sheet 1: `Doctor_Schedules`
Contains the structural work timings for the clinic staff.
* **Doctor**: e.g., Smith, Jones, Lee.
* **Day of Week**: e.g., Monday, Tuesday.
* **Start Time**: e.g., 09:00.
* **End Time**: e.g., 17:00.
* **Slot Duration**: e.g., 60 (minutes).

### Sheet 2: `Availability`
Tracks the exact states of every time slot on every given day.
* **Date**: YYYY-MM-DD
* **Doctor**: Name of the doctor.
* **Time Slot**: HH:MM-HH:MM (e.g., 09:00-10:00)
* **Status**: `PENDING`, `BOOKED`, `AVAILABLE`
* **Patient Phone**: Telegram Chat ID / Details.
* **Booking ID**: Idempotency key / Unique identifier for the booking.
* **Calendar Event ID**: The ID of the Google Calendar event.
* **Version**: Optimistic locking version number.

---

## 3. Global State Management (Redis)

Because HTTP protocols and webhooks are stateless, the Orchestrator uses Redis to persist conversation context between messages. This state dictates what the user is currently doing (`step`) and remembers their selections (e.g., chosen doctor or time).

### State Object Structure
```json
{
    "chat_id": 123456789,
    "user_id": 123456789,
    "username": "johndoe",
    "step": "MENU", // e.g., MENU, AWAITING_DOCTOR, CONFIRMED
    "intent": null, 
    "action": null,
    "context": {
        "selected_doctor": null,
        "selected_date": null,
        "selected_slot": null,
        "booking_id": null,
        "calendar_event_id": null,
        "original_booking_id": null,
        "conversation_history": [
            { "role": "user", "content": "hello", "timestamp": "..." }
        ],
        "slot_options": [],
        "retry_count": 0,
        "idempotency_key": "123456789_123_1680000000",
        "booking_type": "SELF|OTHERS",
        "patient_name": null,
        "patient_phone": null
    },
    "meta": {
        "version": 2,
        "last_updated": "2026-07-10T10:00:00Z",
        "last_activity_ts": 1680000000,
        "message_count": 5,
        "lock_version": 1,
        "total_bookings": 0
    }
}
```

### Self-Healing & Fallbacks in State
* **Corruption Handling**: If state is missing critical fields, it resets to defaults with a system message in history.
* **Version Migration**: Future-proofs by updating `meta.version`.
* **Stuck Sessions (Timeout)**: If a user is stuck in a pending state (`AWAITING_SLOT_CONFIRM`) for >30 minutes, it automatically resets to `MENU`.
* **Retry Limits**: If a user fails validation >5 times, the session is cleared to avoid loops.

---

## 4. Main Orchestrator Workflow

The Orchestrator (`New_AI Telegram Booking System - Main Orchestrator.json`) is the heartbeat of the application.

### Step-by-Step Flow:
1. **Telegram Trigger**: Listens for any incoming messages.
2. **Payload Extraction & Validation (`Extract_Validate_Payload`)**:
   * Drops non-message updates (Edge Case 1).
   * Drops missing Chat IDs (Edge Case 2).
   * Rejects stale messages older than 5 minutes (Edge Case 3).
   * Responds to non-text messages (photos, videos) with a polite prompt to send text (Edge Case 4).
   * Drops empty text / oversized text (>1000 chars) (Edge Cases 5 & 6).
   * Handles hardcoded Bot Commands (`/start`, `/help`, `/menu`, `/book`, `/cancel`) natively to save LLM tokens (Edge Case 7).
   * Rejects forwarded messages (Edge Case 8).
3. **Redis Get Session**: Pulls the state payload for the user's `chat_id`.
4. **Init / Parse State (`Init_Parse_State`)**: Maps defaults, processes corruption/timeouts, checks for explicit reset triggers (e.g., "start over").
5. **Build LLM Context (`Build_LLM_Context`)**: Trims conversation history to the last 12 messages. Wraps business rules, user details, and state summary into a tight prompt.
6. **Gemini Router (Langchain Agent)**: Analyzes the natural language and extracts entities, intents, and actions.
7. **Parse & Validate LLM (`Parse_Validate_LLM`)**: Safely parses Markdown JSON wrappers, falls back to Regex extraction if the LLM hallucinated, and validates all intents/actions against strict Whitelists.
8. **Switch Router (`Switch_Action_Router`)**: Diverts the flow into either a Direct Response (`ASK_USER`, `SHOW_MENU`, `ANSWER_FAQ`) or an `EXECUTE_x_SPOKE` node.
9. **Spoke Execution**: Triggers sub-workflows and waits for their responses.
10. **Final State Merge & Save**: Merges the delta states provided by the LLM and the Spokes, increments counters, sets the `idempotency_key`, saves back to Redis.
11. **Send Telegram Reply**: Dispatches the final text back to the user.

---

## 5. LLM Integration & Persona (Clara)

The system is powered by Google Gemini 2.5 Flash-lite using a highly detailed system prompt to enforce a specific persona.

### Persona Rules:
* **Name**: Clara (Senior Receptionist).
* **Tone**: Exceptionally warm, empathetic, professional.
* **Directives**: Address the user by first name. Validate their feelings (e.g., "I understand scheduling a cardiology visit can feel overwhelming...").
* **Constraint**: Must output strictly valid JSON. Max 400 chars for Telegram replies. Never speak in robotic bullet points.

### Output JSON Schema:
```json
{
  "intent": "BOOK|RESCHEDULE|CANCEL|FAQ|GREETING|UNKNOWN|FRUSTRATED",
  "action": "ASK_USER|FETCH_SLOTS|EXECUTE_BOOKING|...",
  "entities": {
    "doctor": "string or null",
    "date": "YYYY-MM-DD or null",
    "time_slot": "HH:MM-HH:MM or null",
    "booking_type": "SELF|OTHERS",
    "patient_name": "string",
    "patient_phone": "string",
    "confirmation": true/false,
    "slot_index": "number"
  },
  "reply_text": "Empathetic response...",
  "new_step_state": "MENU|AWAITING_DOCTOR|...",
  "preserve_context": { "..." },
  "clear_booking_context": false,
  "requires_sub_workflow": true/false,
  "sub_workflow_name": "BOOK_SPOKE"
}
```

---

## 6. Booking Spoke Workflow

Located in `new_BOOK_SPOKE.json`, this workflow fulfills new appointments.

### Flow Breakdown:
1. **Parse Parent Input**: Receives context from the Orchestrator.
2. **Check Required Entities (`Check_Required_Entities`)**:
   * Evaluates if `doctor` and `date` are present.
   * If `booking_type` is `OTHERS` (booking for someone else), it explicitly ensures `patient_name` and `patient_phone` exist.
   * If any are missing, it short-circuits with an `ASK_USER` response requesting the missing pieces.
3. **Fetch Schedules & Sheets (`Fetch_Schedules`, `Fetch_Slots_From_Sheets`)**: Pulls clinic configuration and current bookings.
4. **Filter & Format Slots (`Filter_Format_Slots`)**:
   * **Self-Healing Duplicate Check**: Verifies if the user *already* has an active booking. If so, prevents duplicate booking and replies with a warning.
   * Calculates the Day of the Week.
   * Checks if the doctor actually has a shift that day.
   * Mathematically generates slots using `Start Time`, `End Time`, and `Slot Duration`.
   * Cross-references against `BOOKED` and `PENDING` statuses to remove taken slots.
   * Sends the user a numbered list of available slots.
5. **Validate Slot Selection (`Validate_Slot_Selection`)**: Processes the user's slot choice (e.g., "1" or "09:00").
6. **Concurrency Check / Lock (`Verify_Lock_Slot`, `Update_Sheet_Pending`)**: 
   * Ensures the slot wasn't taken in the microseconds it took the user to reply.
   * Appends a new row to Google Sheets with status `PENDING` to establish a lock.
7. **Create Calendar Event**: Pushes the appointment to Google Calendar with detailed descriptions.
8. **Finalize (`Update_Sheet_BOOKED`)**: Upgrades the `PENDING` sheet row to `BOOKED` with the calendar event ID. Returns a celebratory response.
9. **Error Rollback**: If calendar creation fails, it throws a polite error and resets to MENU.

---

## 7. Reschedule Spoke Workflow

Located in `NEW_RESCHEDULE_SPOKE.json`, handling date/time modifications for an existing appointment.

### Flow Breakdown:
1. **Lookup Existing Booking**: (Self-Healing) If the Redis session lost the original booking ID, it scans Google Sheets for the user's active booking by their chat ID / username.
2. **Ask Target Date**: If the LLM hasn't extracted a new date, it asks the user.
3. **Fetch & Filter New Slots**: Identical logic to the Booking Spoke, generating mathematical time blocks and removing `BOOKED` items.
4. **Validate Swap (`Validate_Swap`)**:
   * Finds the OLD booking row in the database.
   * Ensures the OLD booking is still active.
5. **Atomic Swap**:
   * **Delete OLD Calendar Event**: Clears it from Google Calendar.
   * **Create NEW Calendar Event**: Books the new time.
   * **Free OLD Slot**: Updates the old Sheet row Status to `AVAILABLE`, clearing the ID/Phone.
   * **Confirm NEW Slot**: Appends/Updates the new row Status to `BOOKED`.
6. **Success Response**: Updates the Redis state context with the new ID, doctor, date, and slot.

---

## 8. Cancellation Spoke Workflow

Located in `CANCEL_SPOKE.json`, this clears up slots for other patients.

### Flow Breakdown:
1. **Check Active Booking**: Ensures `state.context.booking_id` exists.
2. **Confirmation Gate (`Check_Confirmation_Gate`)**:
   * Examines if the user explicitly provided a confirmation word (e.g., "YES", "confirm", "cancel it").
   * If no confirmation is found, it asks the user to type "YES" to prevent accidental cancellations.
3. **Execution**:
   * Deletes the Google Calendar Event (`Delete_Calendar_Event`).
   * Finds the exact row in `Availability` (`Find_Sheet_Row`).
   * Updates the row to clear out Patient Phone, Booking ID, Event ID, and sets status to a blank or `AVAILABLE` state (`Clear_Sheet_Row`).
4. **State Cleanup**: Wipes all booking context variables from the Redis state and resets the step to `MENU`.

---

## 9. FAQ Spoke Workflow

Located in `FAQ_SPOKE.json`, a highly optimized local knowledge base bypassing LLM latency for standard queries.

### Flow Breakdown:
1. **Parse Input**.
2. **FAQ Knowledge Base (`FAQ_Knowledge_Base`)**: 
   * Contains a static dictionary of clinic information (Hours, Location, Contact, Insurance, Doctors, Fees, Cancellation Policy, Preparation, COVID, Emergency).
   * Maps user text using lightweight array matching (e.g., `["location", "address", "where", "find", "direction"]` -> `location`).
   * If a keyword matches, returns the static pre-formatted text.
   * If no match, gracefully lists the topics Clara can help with.
3. **State Integrity**: Does *not* alter the state `step`. If a user asks an FAQ halfway through booking, they will remain on `AWAITING_DATE` after the FAQ is answered.

---

## 10. Error Handling & Self-Healing Mechanisms

A hallmark of this project is its robustness against state loss and race conditions.

* **Idempotency**: Every booking transaction gets a unique `idempotency_key` (`${chatId}_${messageId}_${timestamp}`) attached to the Sheet and State. This prevents duplicate entries if the webhook fires twice.
* **Concurrency Locking**: Slots are appended as `PENDING` before calendar creation. The script verifies that no `BOOKED` or `PENDING` row exists for that slot before locking.
* **Database as Source of Truth**: If Redis is wiped, the `RESCHEDULE_SPOKE` and `BOOK_SPOKE` automatically scan Google Sheets using the user's `chat_id` and `username` to reconstruct their active bookings.
* **LLM Fallbacks**: If the LLM produces invalid JSON or markdown wrappers, the `Parse_Validate_LLM` code node uses regex `/\{[\s\S]*\}/` to extract the JSON. If that fails, it applies a safe fallback intent (`UNKNOWN`) and action (`ASK_USER`).
* **Third-Party Booking Integrity**: The system correctly supports booking for "OTHERS", forcing the collection of a patient name and phone rather than defaulting to the Telegram user's metadata.

---

## 11. Example Conversation Flows

### Scenario A: Booking a new appointment
* **User**: "I need to see a heart doctor tomorrow."
* **Orchestrator**: Identifies intent `BOOK`, Doctor `Smith` (Cardiology), Date `YYYY-MM-DD`. Action -> `FETCH_SLOTS`.
* **Book Spoke**: Fetches availability.
* **Clara (Bot)**: "🩺 *Select Appointment Slot*... Here are the available timings for Dr. Smith... 1. 09:00-10:00..."
* **User**: "1"
* **Book Spoke**: Validates '1'. Locks slot. Creates calendar event.
* **Clara (Bot)**: "🎉 *Wonderful News!* I have successfully scheduled that appointment..."

### Scenario B: Rescheduling an appointment (Self-Healing triggered)
* *(Redis state is accidentally cleared)*
* **User**: "I need to change my appointment to next Friday."
* **Orchestrator**: Identifies intent `RESCHEDULE`, Date `YYYY-MM-DD`.
* **Reschedule Spoke**: `state.booking_id` is null. It scans Google Sheets, finds an active booking for this Chat ID. Extracts old doctor and old date.
* **Reschedule Spoke**: Fetches new slots for next Friday.
* **Clara (Bot)**: "📅 *Select New Timing Slot*... Here are the available timings..."

### Scenario C: Third-Party Booking
* **User**: "Book an appointment for my son with Dr. Lee next Monday."
* **Orchestrator**: Identifies intent `BOOK`, `booking_type` = `OTHERS`. Action -> `ASK_USER`.
* **Book Spoke**: Sees `patient_name` is missing.
* **Clara (Bot)**: "👨‍👩‍👧‍👦 I see you are scheduling this appointment on behalf of someone else! To compile their clinical registration card, could you please tell me the patient's Full Name?"
* **User**: "Tommy Doe"
* **Book Spoke**: Saves `patient_name`. Asks for `patient_phone`.
* **User**: "555-1234"
* **Book Spoke**: Triggers slot fetching and continues the standard flow.

---

*This guide serves as a comprehensive map of the entire n8n architecture, logic models, and code behaviors. Use it for debugging, onboarding, or expanding the system.*
## 12. Simple English Flow of Each Scenario

This section explains exactly what happens behind the scenes for each major action, step-by-step in plain English.

### Scenario 1: The User Starts the Bot or Asks for the Menu
1. **User says**: "/start" or "menu".
2. **The Orchestrator wakes up**: It receives the message from Telegram. It checks to make sure the message isn't too old, isn't empty, and isn't a forwarded message.
3. **Checking memory**: It looks into its memory (Redis) to see if this user has chatted before. If not, it creates a blank memory slate. If the user said a reset word like "menu", it wipes their current booking progress clean.
4. **The Brain (AI) thinks**: It bundles the user's message and their recent chat history, sending it to the AI (Gemini). The AI recognizes the user wants the menu.
5. **The response**: The system bypasses any complex booking steps. It immediately builds a pre-set "Main Menu" text with options like "1. Book, 2. Reschedule" and sends it back to the user via Telegram.

### Scenario 2: The User Wants to Book an Appointment
1. **User says**: "I need to see Dr. Smith next Monday."
2. **The Brain (AI) thinks**: The AI realizes this is a `BOOK` intent. It extracts the doctor's name ("Smith") and figures out the exact date for "next Monday".
3. **The Booking Spoke takes over**: The Orchestrator passes the baton to the Booking Spoke.
4. **Checking missing pieces**: The Spoke checks if it has both the doctor and the date. If the user forgot to mention the date, it would stop and ask them. Since it has both, it proceeds.
5. **Looking up the calendar**: The system silently opens the clinic's Google Sheets. It checks Dr. Smith's schedule for next Monday. It generates all possible 60-minute time slots (e.g., 9:00 AM, 10:00 AM).
6. **Removing taken slots**: It scans the database for any slots that are already marked as `BOOKED` or `PENDING` and removes them from the list.
7. **Presenting options**: The bot sends a message to the user: "Here are the available timings for Dr. Smith... 1. 09:00-10:00, 2. 10:00-11:00. Reply with a number."

### Scenario 3: The User Confirms Their Time Slot
1. **User says**: "1"
2. **Validating the choice**: The Orchestrator remembers the user was asked to pick a slot. The AI processes the "1" and routes it back to the Booking Spoke.
3. **The Race Condition Check**: The system urgently checks Google Sheets one more time. Did someone else book slot #1 in the last 10 seconds? If yes, it tells the user "Sorry, that slot was just taken!" and refreshes the list. 
4. **Locking the slot**: If the slot is free, the system instantly adds a new row to Google Sheets with the status `PENDING`. This "locks" the slot so nobody else can take it.
5. **Creating the Calendar Event**: It connects to Google Calendar and officially creates the event, adding the patient's name and Telegram ID into the event description.
6. **Finalizing**: It updates the Google Sheet row from `PENDING` to `BOOKED`.
7. **Success Message**: The bot sends a celebratory confirmation message to the user with all their appointment details.

### Scenario 4: The User Needs to Reschedule
1. **User says**: "Can we change my appointment to tomorrow?"
2. **Finding the old booking**: The AI recognizes the `RESCHEDULE` intent. The Reschedule Spoke takes over. It looks into the user's memory to find their current booking ID. If the memory was lost, it automatically searches the Google Sheets database to find their active booking.
3. **Fetching new slots**: Just like booking, it looks up the doctor's availability for "tomorrow" and presents a list of free time slots.
4. **User picks a new time**: The user replies with a number.
5. **The Swap**: The system performs a delicate swap. It deletes the old Google Calendar event. It creates a brand new Google Calendar event for the new time.
6. **Database cleanup**: It finds the old row in Google Sheets and changes its status back to `AVAILABLE`. It then marks the new time slot as `BOOKED`.
7. **Confirmation**: The user receives a message confirming their appointment has been successfully moved.

### Scenario 5: The User Cancels Their Appointment
1. **User says**: "Cancel my appointment."
2. **Are you sure?**: The AI recognizes the `CANCEL` intent. To prevent accidental cancellations, the Cancel Spoke intervenes and asks: "Are you sure? Type YES to confirm."
3. **User says**: "YES".
4. **Execution**: The Cancel Spoke connects to Google Calendar and deletes the event. It goes into Google Sheets, finds the specific row for that booking, and erases the user's details, freeing up the time slot.
5. **Memory wiped**: The system wipes the booking details from the user's Redis memory so they can start fresh next time.
6. **Confirmation**: The bot notifies the user that the cancellation was successful.

### Scenario 6: The User Asks a General Question (FAQ)
1. **User says**: "What time do you open?"
2. **AI recognizes FAQ**: The AI flags this as an `FAQ` intent.
3. **The FAQ Spoke acts**: Instead of doing complex database searches, the FAQ Spoke simply matches the word "open" against a built-in knowledge base.
4. **Instant reply**: It instantly replies with the clinic's operating hours. 
5. **Seamless return**: Behind the scenes, the system doesn't change the user's "step". If they were halfway through booking an appointment when they asked the question, they can seamlessly resume booking right after getting their answer.

---

## 13. Complete Workflow Code (JSON)

Below is the complete source code for all n8n workflows in this project. You can copy the contents of these blocks and paste them directly into an n8n canvas to import the workflows.

### New_AI Telegram Booking System - Main Orchestrator.json

``json
{
  "name": "New_AI Telegram Booking System - Main Orchestrator",
  "nodes": [
    {
      "parameters": {
        "updates": [
          "message"
        ],
        "additionalFields": {}
      },
      "type": "n8n-nodes-base.telegramTrigger",
      "typeVersion": 1.2,
      "position": [
        -2672,
        288
      ],
      "id": "4b00c89c-c5ec-49dd-8283-9e63e32236b9",
      "name": "Telegram Bot",
      "webhookId": "telegram-booking-webhook",
      "credentials": {
        "telegramApi": {
          "id": "XWY8EyYqQXb9Aj1W",
          "name": "Telegram account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "// ============================================\n// PAYLOAD EXTRACTION & VALIDATION\n// ============================================\n\nconst body = $input.first().json;\n\n// Edge Case 1: No message object\nif (!body.message) {\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\tis_valid: false,\n\t\t\t\tskip_reason: \"NO_MESSAGE_OBJECT\",\n\t\t\t\tshould_reply: false,\n\t\t\t\tnote: \"Non-message Telegram update\"\n\t\t\t}\n\t\t}\n\t];\n}\n\nconst message = body.message;\n\nconst chatId = message.chat ? message.chat.id : null;\nconst messageId = message.message_id;\nconst timestamp = message.date;\n\nconst now = Math.floor(Date.now() / 1000);\nconst messageAge = now - timestamp;\n\n// Edge Case 2: Missing Chat ID\nif (!chatId) {\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\tis_valid: false,\n\t\t\t\tskip_reason: \"MISSING_CHAT_ID\",\n\t\t\t\tshould_reply: false\n\t\t\t}\n\t\t}\n\t];\n}\n\n// Edge Case 3: Old Message\nif (messageAge > 300) {\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\tis_valid: false,\n\t\t\t\tskip_reason: \"STALE_MESSAGE\",\n\t\t\t\tmessage_age_seconds: messageAge,\n\t\t\t\tshould_reply: false,\n\t\t\t\tnote: \"Message older than 5 minutes\"\n\t\t\t}\n\t\t}\n\t];\n}\n\n// Detect Message Type\nconst ignoredKeys = [\n\t'message_id',\n\t'from',\n\t'chat',\n\t'date',\n\t'edit_date',\n\t'forward_from',\n\t'forward_date',\n\t'reply_to_message',\n\t'via_bot',\n\t'entities',\n\t'caption_entities',\n\t'author_signature',\n\t'sender_chat',\n\t'is_automatic_forward',\n\t'has_protected_content',\n\t'media_group_id'\n];\n\nconst messageType = Object.keys(message).find(\n\tkey => !ignoredKeys.includes(key)\n);\n\n// Edge Case 4: Non-text messages\nif (!message.text) {\n\n\tconst typeResponses = {\n\t\tphoto: \"📷 I can only process text messages for bookings. Please type your request.\",\n\t\tvideo: \"🎥 I can't process videos. Please type your request.\",\n\t\tvoice: \"🎙️ I can't process voice messages. Please type your request.\",\n\t\taudio: \"🎵 I can't process audio files. Please type your request.\",\n\t\tdocument: \"📄 I can't process documents. Please type your request.\",\n\t\tlocation: \"📍 I received your location. Please type your booking request.\",\n\t\tsticker: \"😊 Please send a text message for booking assistance.\",\n\t\tcontact: \"👤 Please type your request.\",\n\t\tpoll: \"📊 I can't process polls. Please type your request.\"\n\t};\n\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\tis_valid: false,\n\t\t\t\tskip_reason: \"NON_TEXT_MESSAGE\",\n\t\t\t\tmessage_type: messageType || \"unknown\",\n\t\t\t\tshould_reply: true,\n\t\t\t\treply_text:\n\t\t\t\t\ttypeResponses[messageType] ||\n\t\t\t\t\t\"⚠️ Please send a text message.\",\n\t\t\t\tchat_id: chatId\n\t\t\t}\n\t\t}\n\t];\n}\n\n// Edge Case 5: Empty Text\nconst text = message.text.trim();\n\nif (!text) {\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\tis_valid: false,\n\t\t\t\tskip_reason: \"EMPTY_MESSAGE\",\n\t\t\t\tshould_reply: true,\n\t\t\t\treply_text:\n\t\t\t\t\t\"🤔 I didn't receive any text.\\n\\nSay 'menu' to see options.\",\n\t\t\t\tchat_id: chatId\n\t\t\t}\n\t\t}\n\t];\n}\n\n// Edge Case 6: Message Too Long\nif (text.length > 1000) {\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\tis_valid: false,\n\t\t\t\tskip_reason: \"MESSAGE_TOO_LONG\",\n\t\t\t\tmessage_length: text.length,\n\t\t\t\tshould_reply: true,\n\t\t\t\treply_text:\n\t\t\t\t\t\"⚠️ Your message is too long. Please keep it brief.\",\n\t\t\t\tchat_id: chatId\n\t\t\t}\n\t\t}\n\t];\n}\n\n// Edge Case 7: Bot Commands\nif (text.startsWith('/') && text !== '/start') {\n\n\tconst commandResponses = {\n\t\t'/help':\n\t\t\t\"🆘 Help Menu\\n\\n\" +\n\t\t\t\"• book - Make appointment\\n\" +\n\t\t\t\"• reschedule - Change booking\\n\" +\n\t\t\t\"• cancel - Cancel booking\\n\" +\n\t\t\t\"• view - View booking\\n\" +\n\t\t\t\"• menu - Show options\",\n\n\t\t'/menu': 'MENU_REQUEST',\n\t\t'/book': 'BOOK_REQUEST',\n\t\t'/cancel': 'CANCEL_REQUEST'\n\t};\n\n\tconst command = text.split(' ')[0];\n\tconst response = commandResponses[command];\n\n\tif (response && response.includes('_REQUEST')) {\n\n\t\treturn [\n\t\t\t{\n\t\t\t\tjson: {\n\t\t\t\t\tis_valid: true,\n\t\t\t\t\tchat_id: chatId,\n\t\t\t\t\tuser_id: message.from ? message.from.id : null,\n\t\t\t\t\tmessage_id: messageId,\n\t\t\t\t\tmessage_text: text,\n\t\t\t\t\tmessage_type: \"command\",\n\t\t\t\t\tcommand: command,\n\t\t\t\t\timplicit_intent: response.replace('_REQUEST', ''),\n\t\t\t\t\ttimestamp: timestamp,\n\t\t\t\t\traw_body: body,\n\t\t\t\t\tshould_reply: true\n\t\t\t\t}\n\t\t\t}\n\t\t];\n\t}\n\n\tif (response) {\n\t\treturn [\n\t\t\t{\n\t\t\t\tjson: {\n\t\t\t\t\tis_valid: false,\n\t\t\t\t\tskip_reason: \"BOT_COMMAND_HANDLED\",\n\t\t\t\t\tshould_reply: true,\n\t\t\t\t\treply_text: response,\n\t\t\t\t\tchat_id: chatId\n\t\t\t\t}\n\t\t\t}\n\t\t];\n\t}\n}\n\n// Edge Case 8: Forwarded Messages\nif (message.forward_from || message.forward_date) {\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\tis_valid: false,\n\t\t\t\tskip_reason: \"FORWARDED_MESSAGE\",\n\t\t\t\tshould_reply: true,\n\t\t\t\treply_text:\n\t\t\t\t\t\"⚠️ I don't process forwarded messages. Please type your own request.\",\n\t\t\t\tchat_id: chatId\n\t\t\t}\n\t\t}\n\t];\n}\n\n// ============================================\n// VALID MESSAGE\n// ============================================\n\nreturn [\n\t{\n\t\tjson: {\n\t\t\tis_valid: true,\n\t\t\tchat_id: chatId,\n\t\t\tuser_id: message.from ? message.from.id : null,\n\t\t\tfirst_name: message.from ? message.from.first_name : null,\n\t\t\tusername: message.from ? message.from.username : null,\n\t\t\tmessage_id: messageId,\n\t\t\tmessage_text: text,\n\t\t\tmessage_type: \"text\",\n\t\t\ttimestamp: timestamp,\n\t\t\traw_body: body,\n\t\t\tshould_reply: true,\n\t\t\tis_fresh_command: text === '/start'\n\t\t}\n\t}\n];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -2464,
        288
      ],
      "id": "4f0b3213-92b1-4470-92df-2f616dc0b333",
      "name": "Extract_Validate_Payload"
    },
    {
      "parameters": {
        "operation": "get",
        "propertyName": "chatID",
        "key": "={{ 'telegram:session:' + $json.chat_id }}",
        "options": {}
      },
      "type": "n8n-nodes-base.redis",
      "typeVersion": 1,
      "position": [
        -2272,
        288
      ],
      "id": "6aa0184f-d06a-44ff-8e00-5100b3ec679e",
      "name": "Redis_Get_Session",
      "credentials": {
        "redis": {
          "id": "IFmfKowHmcx4QSHk",
          "name": "Redis account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "// ============================================\n// STATE INITIALIZATION & RECOVERY\n// Production-grade: handles corruption, timeouts, version migration\n// ============================================\n\nconst input = $('Extract_Validate_Payload').first().json;\nconst chatId = input.chat_id;\nconst messageText = input.message_text || '';  // FIX: null safety\nconst messageId = input.message_id;\nconst username = input.username || input.first_name || 'user';\nconst rawState = $('Redis_Get_Session').first().json; // Redis output is second input\n\nconst now = new Date().toISOString();\nconst nowTs = Date.now();\n\n// Default state template\nconst defaultState = {\n    chat_id: chatId,\n    user_id: input.user_id,\n    username: username,\n    step: \"MENU\",\n    intent: null,\n    action: null,\n    context: {\n        selected_doctor: null,\n        selected_date: null,\n        selected_slot: null,\n        booking_id: null,\n        calendar_event_id: null,\n        original_booking_id: null,\n        original_calendar_event_id: null,\n        conversation_history: [],\n        slot_options: [],\n        last_question: null,\n        retry_count: 0,\n        idempotency_key: null,\n        command_used: false\n    },\n    meta: {\n        version: 2,\n        created_at: now,\n        last_updated: now,\n        last_activity_ts: nowTs,\n        message_count: 0,\n        lock_version: 1,\n        total_bookings: 0,\n        total_reschedules: 0,\n        total_cancels: 0\n    }\n};\n\nlet state;\nlet isFreshSession = false;\n\n// No state found in Redis\nif (rawState === null || rawState === undefined) {\n    state = JSON.parse(JSON.stringify(defaultState));\n    isFreshSession = true;\n} else {\n    try {\n        state = typeof rawState === 'string' ? JSON.parse(rawState) : rawState;\n\n        // Edge case: Corrupted state (missing critical fields)\n        if (!state.chat_id || !state.step || !state.context || !state.meta) {\n            console.warn(`[STATE_RECOVERY] Corrupted state for ${chatId}, resetting`);\n            state = JSON.parse(JSON.stringify(defaultState));\n            state.context.conversation_history = [{\n                role: \"system\",\n                content: \"Session recovered from corrupted state\",\n                timestamp: now\n            }];\n        }\n\n        // Edge case: Version migration (future-proofing)\n        if (!state.meta || state.meta.version < 2) {\n            console.log(`[STATE_MIGRATION] Upgrading state from v${state.meta?.version || 'unknown'} to v2`);\n            state.meta = { ...defaultState.meta, ...state.meta, version: 2 };\n            state.meta.total_bookings = state.meta.total_bookings || 0;\n            state.meta.total_reschedules = state.meta.total_reschedules || 0;\n            state.meta.total_cancels = state.meta.total_cancels || 0;\n        }\n\n        // Edge case: Stuck in intermediate state for >30 minutes\n        const lastActivity = state.meta.last_activity_ts || 0;\n        const inactiveTime = nowTs - lastActivity;\n        const stuckStates = [\n            \"AWAITING_SLOT_CONFIRM\", \n            \"CONFIRM_BOOKING\", \n            \"CONFIRM_CANCEL\", \n            \"CONFIRM_RESCHEDULE\", \n            \"PENDING_LOCK\",\n            \"AWAITING_RESCHEDULE_SLOT\"\n        ];\n\n        if (inactiveTime > 1800000 && stuckStates.includes(state.step)) {\n            console.warn(`[STATE_TIMEOUT] Session stuck for ${Math.floor(inactiveTime/60000)}min, resetting to MENU`);\n            state.step = \"MENU\";\n            state.intent = null;\n            state.action = null;\n            state.context.selected_doctor = null;\n            state.context.selected_date = null;\n            state.context.selected_slot = null;\n            state.context.booking_id = null;\n            state.context.calendar_event_id = null;\n            state.context.retry_count = 0;\n            state.context.conversation_history.push({\n                role: \"system\",\n                content: `Session timed out after ${Math.floor(inactiveTime/60000)} minutes. Reset to menu.`,\n                timestamp: now\n            });\n        }\n\n        // Edge case: Too many retries (possible loop/stuck user)\n        if (state.context.retry_count > 5) {\n            console.warn(`[STATE_RETRY_LIMIT] Too many retries (${state.context.retry_count}), resetting`);\n            state.step = \"MENU\";\n            state.intent = null;\n            state.action = null;\n            state.context.retry_count = 0;\n            state.context.conversation_history.push({\n                role: \"system\",\n                content: \"Too many retries. Reset to menu.\",\n                timestamp: now\n            });\n        }\n\n    } catch (e) {\n        console.error(`[STATE_ERROR] Unparseable state for ${chatId}: ${e.message}`);\n        state = JSON.parse(JSON.stringify(defaultState));\n        state.context.conversation_history = [{\n            role: \"system\",\n            content: `Session reset due to error: ${e.message}`,\n            timestamp: now\n        }];\n    }\n}\n\n// Update activity timestamp\nstate.meta.last_activity_ts = nowTs;\nstate.meta.message_count = (state.meta.message_count || 0) + 1;\n\n// Generate idempotency key for this transaction\nstate.context.idempotency_key = `${chatId}_${messageId}_${nowTs}`;\n\n// Add user message to history\nstate.context.conversation_history.push({\n    role: \"user\",\n    content: messageText,\n    message_id: messageId,\n    timestamp: now\n});\n\n// Trim history to last 20 messages (token + memory optimization)\nif (state.context.conversation_history.length > 20) {\n    state.context.conversation_history = state.context.conversation_history.slice(-20);\n}\n\n// Detect if user said \"menu\", \"start over\", \"reset\" — FIX: null safety\nconst resetTriggers = ['menu', 'start over', 'reset', 'restart', 'begin', 'start again'];\nconst shouldReset = messageText ? resetTriggers.some(trigger => messageText.toLowerCase().includes(trigger)) : false;\n\nif (shouldReset && !isFreshSession) {\n    console.log(`[STATE_RESET] User requested reset via: \"${messageText}\"`);\n    state.step = \"MENU\";\n    state.intent = null;\n    state.action = null;\n    state.context.selected_doctor = null;\n    state.context.selected_date = null;\n    state.context.selected_slot = null;\n    state.context.booking_id = null;\n    state.context.calendar_event_id = null;\n    state.context.slot_options = [];\n    state.context.retry_count = 0;\n    state.context.conversation_history.push({\n        role: \"system\",\n        content: \"User requested reset. Cleared booking context.\",\n        timestamp: now\n    });\n}\n\nreturn [{\n    json: {\n        chat_id: chatId,\n        user_id: input.user_id,\n        username: username,\n        message_text: messageText,\n        message_id: messageId,\n        current_state: state,\n        is_fresh_session: isFreshSession,\n        system_time: now,\n        should_reply: true,\n        user_requested_reset: shouldReset\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -2064,
        288
      ],
      "id": "202b3444-b87e-44a6-9a85-08a6d9baed28",
      "name": "Init_Parse_State"
    },
    {
      "parameters": {
        "jsCode": "// ============================================\n// LLM CONTEXT BUILDER\n// ============================================\n\nconst input = $input.first().json;\n\nconst state = input.current_state || {};\nconst chatId = input.chat_id;\nconst message = input.message_text || \"\";\nconst now = input.system_time || new Date().toISOString();\n\n// Safe access\nconst context = state.context || {};\nconst meta = state.meta || {};\n\n// ============================================\n// Conversation History\n// ============================================\n\nconst history = (context.conversation_history || []).slice(-12);\n\nconst formattedHistory = history\n\t.map(h => {\n\n\t\tconst prefix =\n\t\t\th.role === 'user'\n\t\t\t\t? 'User'\n\t\t\t\t: h.role === 'assistant'\n\t\t\t\t? 'Assistant'\n\t\t\t\t: 'System';\n\n\t\treturn `${prefix}: ${h.content}`;\n\t})\n\t.join('\\n');\n\n// ============================================\n// Context Summary\n// ============================================\n\nconst contextSummary = {};\n\nif (state.step) {\n\tcontextSummary.current_step = state.step;\n}\n\nif (state.intent) {\n\tcontextSummary.current_intent = state.intent;\n}\n\nif (context.selected_doctor) {\n\tcontextSummary.selected_doctor = context.selected_doctor;\n}\n\nif (context.selected_date) {\n\tcontextSummary.selected_date = context.selected_date;\n}\n\nif (context.selected_slot) {\n\tcontextSummary.selected_slot = context.selected_slot;\n}\n\nif (context.booking_id) {\n\tcontextSummary.has_booking = true;\n\tcontextSummary.booking_id = context.booking_id;\n}\n\n// ============================================\n// Business Rules\n// ============================================\n\nconst rules = [\n\t\"Extract intent: BOOK, RESCHEDULE, CANCEL, FAQ, GREETING, UNKNOWN\",\n\n\t\"BOOK needs: doctor + date → FETCH_SLOTS → slot selection → EXECUTE_BOOKING\",\n\n\t\"RESCHEDULE needs: existing booking_id + new date/slot\",\n\n\t\"CANCEL needs: existing booking_id + explicit YES confirmation\",\n\n\t\"FAQ: answer but preserve booking context, do not reset step\",\n\n\t\"Date format: YYYY-MM-DD. Convert relative dates using current_time\",\n\n\t\"confirmation=true ONLY if user says yes/confirm/delete/proceed\",\n\n\t\"If user says menu/start over/reset → action=SHOW_MENU\",\n\n\t\"If frustrated (caps/repeated questions) → ESCALATE_HUMAN\",\n\n\t\"Slot selection: user replies with number or time like 14:00\"\n];\n\n// ============================================\n// Final LLM Context\n// ============================================\n\nconst llmContext = {\n\tsystem_context: {\n\t\tcurrent_time: now,\n\t\tuser_chat_id: chatId,\n\t\tusername: state.username || \"\",\n\t\tsession_age_messages: meta.message_count || 0,\n\t\tis_fresh_session: input.is_fresh_session || false\n\t},\n\n\tuser_message: message,\n\n\tconversation_state: contextSummary,\n\n\tconversation_history: formattedHistory,\n\n\tbusiness_rules: rules\n};\n\n// ============================================\n// Return\n// ============================================\n\nreturn [\n\t{\n\t\tjson: {\n\t\t\t...input,\n\t\t\tllm_context: llmContext,\n\t\t\tstate_summary: contextSummary\n\t\t}\n\t}\n];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -1872,
        288
      ],
      "id": "f9d3e819-18b7-4568-84a1-edbbfad82fb5",
      "name": "Build_LLM_Context"
    },
    {
      "parameters": {
        "modelName": "models/gemini-2.5-flash-lite",
        "options": {
          "maxOutputTokens": 800,
          "temperature": 0.1
        }
      },
      "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
      "typeVersion": 1,
      "position": [
        -1696,
        560
      ],
      "id": "0d9ccb76-51a4-471a-be83-a205da596daa",
      "name": "Google Gemini Chat Model",
      "credentials": {
        "googlePalmApi": {
          "id": "0h8cRy1yXPWfuNbF",
          "name": "Google Gemini(PaLM) Api account 2"
        }
      }
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "={{ $json.message_text }}",
        "options": {
          "systemMessage": "You are Clara, the exceptionally warm, empathetic, and professional clinic coordinator and senior receptionist at our premium medical clinic. Your primary goal is to help patients book, reschedule, or cancel doctor appointments. You must output strictly valid JSON with no markdown wrapping.\n\nCLARA'S PERSONA:\n- You speak conversationally, naturally, and warmly. Address the user by their first name ({{ $json.username }}) often.\n- Show deep empathy. If a patient is booking a specialized department (e.g., Cardiology with Dr. Smith), warmly validate them: \"I understand that scheduling a cardiology visit can feel a bit overwhelming, {{ $json.username }}, but please rest assured Dr. Smith is incredibly caring and has helped so many. Let's find a time that works best for you...\"\n- If they are cancelling or rescheduling, show understanding: \"Oh, I completely understand, {{ $json.username }}. Life happens! Let's get that squared away...\"\n- Never speak in dry, robotic bullet points or lists in your conversational reply. Keep the text engaging and natural. Max 400 chars for Telegram.\n\nCURRENT CLINIC STATUS:\n- TIME: {{ $json.system_time }}\n- USER: {{ $json.username }} (chat: {{ $json.chat_id }})\n\nAVAILABLE DOCTORS:\n1. Dr. Smith - Cardiology (Mon-Fri, 09:00-17:00)\n2. Dr. Jones - Dermatology (Mon-Wed-Fri, 10:00-16:00)\n3. Dr. Lee - General Medicine (Mon-Sat, 08:00-18:00)\n\nBUSINESS RULES & ENTITY EXTRACTION:\n- BOOK: needs doctor + date -> FETCH_SLOTS -> user picks index -> EXECUTE_BOOKING.\n- THIRD-PARTY BOOKINGS: If the user says they want to book for their child, spouse, or someone else:\n  1. Set booking_type = \"OTHERS\".\n  2. Extract patient_name and patient_phone.\n  3. If patient_name or patient_phone are missing, set action = \"ASK_USER\" and warmly ask the user to provide the patient's Full Name and Contact Phone Number so you can list availability for them.\n- If booking for themselves, set booking_type = \"SELF\" and carry over.\n- Date format: YYYY-MM-DD. Convert relative terms like \"tomorrow\" timezone-safely based on CURRENT TIME.\n- Reset words (menu/start over) -> SHOW_MENU.\n- Frustrated user -> ESCALATE_HUMAN.\n\nSTRICT JSON OUTPUT FORMAT:\n{\n  \"intent\": \"BOOK|RESCHEDULE|CANCEL|FAQ|GREETING|UNKNOWN|FRUSTRATED\",\n  \"action\": \"ASK_USER|FETCH_SLOTS|EXECUTE_BOOKING|EXECUTE_RESCHEDULE|EXECUTE_CANCEL|ANSWER_FAQ|SHOW_MENU|ESCALATE_HUMAN\",\n  \"entities\": {\n    \"doctor\": \"string or null\",\n    \"date\": \"YYYY-MM-DD or null\",\n    \"time_slot\": \"HH:MM-HH:MM or null\",\n    \"booking_type\": \"SELF|OTHERS|null\",\n    \"patient_name\": \"string or null\",\n    \"patient_phone\": \"string or null\",\n    \"confirmation\": \"boolean\",\n    \"slot_index\": \"number or null\",\n    \"reschedule_target_date\": \"YYYY-MM-DD or null\",\n    \"reschedule_target_slot\": \"HH:MM-HH:MM or null\"\n  },\n  \"reply_text\": \"Empathetic natural language response from Clara\",\n  \"new_step_state\": \"MENU|AWAITING_DOCTOR|AWAITING_DATE|AWAITING_SLOT_CONFIRM|CONFIRM_BOOKING|CONFIRM_RESCHEDULE|CONFIRM_CANCEL|CONFIRMED|FAQ_ANSWERED\",\n  \"preserve_context\": {\n    \"selected_doctor\": \"carry over or null\",\n    \"selected_date\": \"carry over or null\",\n    \"selected_slot\": \"carry over or null\",\n    \"booking_type\": \"SELF|OTHERS|null\",\n    \"patient_name\": \"string or null\",\n    \"patient_phone\": \"string or null\",\n    \"booking_id\": \"carry over or null\",\n    \"calendar_event_id\": \"carry over or null\"\n  },\n  \"clear_booking_context\": \"boolean\",\n  \"escalation_reason\": \"string or null\",\n  \"requires_sub_workflow\": \"boolean\",\n  \"sub_workflow_name\": \"BOOK_SPOKE|RESCHEDULE_SPOKE|CANCEL_SPOKE|FAQ_SPOKE|HUMAN_SPOKE or null\",\n  \"confidence\": \"number 0-1\"\n}"
        }
      },
      "type": "@n8n/n8n-nodes-langchain.agent",
      "typeVersion": 3.1,
      "position": [
        -1552,
        288
      ],
      "id": "62d07944-bea9-47b0-b0fe-11d571189bb9",
      "name": "Gemini_Router"
    },
    {
      "parameters": {
        "jsCode": "// ============================================\n// LLM OUTPUT VALIDATION & SANITIZATION\n// Production-safe n8n Code Node\n// ============================================\n\nconst input = $('Gemini_Router').first().json;\n\nconst state = input.current_state || {};\n\nconst rawOutput =\n\tinput.output ||\n\tinput.text ||\n\tinput.content ||\n\t(input.message ? input.message.content : '') ||\n\t'';\n\nlet llmOutput = null;\n\nlet parseError = null;\n\n// ============================================\n// STEP 1: CLEAN MARKDOWN\n// ============================================\n\nlet cleanedOutput = rawOutput;\n\nif (typeof rawOutput === 'string') {\n\n\tcleanedOutput = rawOutput\n\t\t.replace(/```json\\s*/g, '')\n\t\t.replace(/```\\s*/g, '')\n\t\t.trim();\n}\n\n// ============================================\n// STEP 2: PARSE JSON\n// ============================================\n\ntry {\n\n\tllmOutput =\n\t\ttypeof cleanedOutput === 'string'\n\t\t\t? JSON.parse(cleanedOutput)\n\t\t\t: cleanedOutput;\n\n} catch (e) {\n\n\tparseError = e.message;\n\n\tconsole.error(\n\t\t`[LLM_PARSE_ERROR] Failed to parse: ${e.message}`\n\t);\n\n\tconsole.error(\n\t\t`[LLM_RAW_OUTPUT] ${String(rawOutput).substring(0, 200)}`\n\t);\n}\n\n// ============================================\n// STEP 3: REGEX RECOVERY\n// ============================================\n\nif (!llmOutput && typeof rawOutput === 'string') {\n\n\tconst jsonMatch = rawOutput.match(/\\{[\\s\\S]*\\}/);\n\n\tif (jsonMatch) {\n\n\t\ttry {\n\n\t\t\tllmOutput = JSON.parse(jsonMatch[0]);\n\n\t\t\tparseError = null;\n\n\t\t\tconsole.log(\n\t\t\t\t'[LLM_RECOVER] Extracted JSON via regex'\n\t\t\t);\n\n\t\t} catch (e2) {\n\n\t\t\tconsole.error(\n\t\t\t\t'[LLM_RECOVER_FAILED] Regex extraction failed'\n\t\t\t);\n\t\t}\n\t}\n}\n\n// ============================================\n// VALIDATION ARRAYS\n// ============================================\n\nconst validActions = [\n\t'ASK_USER',\n\t'FETCH_SLOTS',\n\t'EXECUTE_BOOKING',\n\t'EXECUTE_RESCHEDULE',\n\t'EXECUTE_CANCEL',\n\t'ANSWER_FAQ',\n\t'SHOW_MENU',\n\t'ESCALATE_HUMAN',\n\t'RESET_SESSION'\n];\n\nconst validSteps = [\n\t'MENU',\n\t'AWAITING_DOCTOR',\n\t'AWAITING_DATE',\n\t'AWAITING_SLOT_CONFIRM',\n\t'CONFIRM_BOOKING',\n\t'CONFIRM_RESCHEDULE',\n\t'CONFIRM_CANCEL',\n\t'CONFIRMED',\n\t'AWAITING_RESCHEDULE_DATE',\n\t'AWAITING_RESCHEDULE_SLOT',\n\t'FAQ_ANSWERED'\n];\n\nconst validIntents = [\n\t'BOOK',\n\t'RESCHEDULE',\n\t'CANCEL',\n\t'FAQ',\n\t'GREETING',\n\t'UNKNOWN',\n\t'MENU_REQUEST',\n\t'FRUSTRATED'\n];\n\n// ============================================\n// SUB-WORKFLOW MAP\n// ============================================\n\nconst subWorkflowMap = {\n\n\tEXECUTE_BOOKING: 'BOOK_SPOKE',\n\n\tEXECUTE_RESCHEDULE: 'RESCHEDULE_SPOKE',\n\n\tEXECUTE_CANCEL: 'CANCEL_SPOKE',\n\n\tANSWER_FAQ: 'FAQ_SPOKE',\n\n\tESCALATE_HUMAN: 'HUMAN_SPOKE'\n};\n\n// ============================================\n// STEP 4: FALLBACK\n// ============================================\n\nif (!llmOutput || typeof llmOutput !== 'object') {\n\n\tconsole.warn(\n\t\t'[LLM_FALLBACK] Using fallback due to parse failure'\n\t);\n\n\treturn [\n\t\t{\n\t\t\tjson: {\n\t\t\t\t...input,\n\n\t\t\t\tllm_valid: false,\n\n\t\t\t\tllm_error:\n\t\t\t\t\tparseError || 'NO_VALID_OUTPUT',\n\n\t\t\t\taction: 'ASK_USER',\n\n\t\t\t\tintent: 'UNKNOWN',\n\n\t\t\t\treply_text:\n\t\t\t\t\t\"I'm not sure I understood. Could you rephrase? Say 'menu' to see options or 'book' to start booking.\",\n\n\t\t\t\tnew_step_state:\n\t\t\t\t\tstate.step || 'MENU',\n\n\t\t\t\tentities: {},\n\n\t\t\t\trequires_sub_workflow: false,\n\n\t\t\t\tsub_workflow_name: null,\n\n\t\t\t\tclear_booking_context: false,\n\n\t\t\t\tconfidence: 0.1\n\t\t\t}\n\t\t}\n\t];\n}\n\n// ============================================\n// STEP 5: ACTION VALIDATION\n// ============================================\n\nif (!validActions.includes(llmOutput.action)) {\n\n\tconsole.warn(\n\t\t`[LLM_INVALID_ACTION] ${llmOutput.action}`\n\t);\n\n\tllmOutput.action = 'ASK_USER';\n\n\tllmOutput.fallback_action = 'SHOW_MENU';\n}\n\n// ============================================\n// STEP VALIDATION\n// ============================================\n\nif (!validSteps.includes(llmOutput.new_step_state)) {\n\n\tllmOutput.new_step_state =\n\t\tstate.step || 'MENU';\n}\n\n// ============================================\n// INTENT VALIDATION\n// ============================================\n\nif (!validIntents.includes(llmOutput.intent)) {\n\n\tllmOutput.intent = 'UNKNOWN';\n}\n\n// ============================================\n// LOW CONFIDENCE HANDLING\n// ============================================\n\nif (\n\t(llmOutput.confidence || 1) < 0.4 &&\n\tllmOutput.action !== 'ESCALATE_HUMAN'\n) {\n\n\tconsole.log(\n\t\t`[LLM_LOW_CONFIDENCE] ${llmOutput.confidence}`\n\t);\n\n\tllmOutput.action = 'ASK_USER';\n\n\tllmOutput.reply_text =\n\t\t\"I'm not entirely sure. \" +\n\t\t(llmOutput.reply_text ||\n\t\t\t'Could you clarify?');\n}\n\n// ============================================\n// REPLY LENGTH CHECK\n// ============================================\n\nif (\n\tllmOutput.reply_text &&\n\tllmOutput.reply_text.length > 500\n) {\n\n\tllmOutput.reply_text =\n\t\tllmOutput.reply_text.substring(0, 497) +\n\t\t'...';\n}\n\n// ============================================\n// EMPTY REPLY FALLBACK\n// ============================================\n\nif (\n\t!llmOutput.reply_text ||\n\tllmOutput.reply_text.trim().length === 0\n) {\n\n\tconst defaults = {\n\n\t\tASK_USER:\n\t\t\t'Could you provide more details?',\n\n\t\tFETCH_SLOTS:\n\t\t\t'Let me check availability...',\n\n\t\tEXECUTE_BOOKING:\n\t\t\t'Processing your booking...',\n\n\t\tEXECUTE_RESCHEDULE:\n\t\t\t'Processing your reschedule...',\n\n\t\tEXECUTE_CANCEL:\n\t\t\t'Processing cancellation...',\n\n\t\tANSWER_FAQ:\n\t\t\t\"Here's what I found:\",\n\n\t\tSHOW_MENU: `🏥 Main Menu\n\n1. Book Appointment\n2. Reschedule\n3. Cancel\n4. View Booking\n5. FAQ`,\n\n\t\tESCALATE_HUMAN:\n\t\t\t'Connecting you to support...',\n\n\t\tRESET_SESSION:\n\t\t\t'Starting fresh! How can I help?'\n\t};\n\n\tllmOutput.reply_text =\n\t\tdefaults[llmOutput.action] ||\n\t\t'How can I help you?';\n}\n\n// ============================================\n// ENTITY SANITIZATION\n// ============================================\n\nllmOutput.entities =\n\tllmOutput.entities || {};\n\nllmOutput.entities.doctor =\n\tllmOutput.entities.doctor || null;\n\nllmOutput.entities.date =\n\tllmOutput.entities.date || null;\n\nllmOutput.entities.time_slot =\n\tllmOutput.entities.time_slot || null;\n\nllmOutput.entities.confirmation =\n\t!!llmOutput.entities.confirmation;\n\nllmOutput.entities.slot_index =\n\tllmOutput.entities.slot_index || null;\n\nllmOutput.entities.booking_type = llmOutput.entities.booking_type || null;\nllmOutput.entities.patient_name = llmOutput.entities.patient_name || null;\nllmOutput.entities.patient_phone = llmOutput.entities.patient_phone || null;\n\nllmOutput.entities.reschedule_target_date =\n\tllmOutput.entities.reschedule_target_date || null;\n\nllmOutput.entities.reschedule_target_slot =\n\tllmOutput.entities.reschedule_target_slot || null;\n\n// ============================================\n// PRESERVE CONTEXT\n// ============================================\n\nllmOutput.preserve_context =\n\tllmOutput.preserve_context || {};\n\n// ============================================\n// SUB-WORKFLOW\n// ============================================\n\nllmOutput.requires_sub_workflow =\n\t!!subWorkflowMap[llmOutput.action];\n\nllmOutput.sub_workflow_name =\n\tsubWorkflowMap[llmOutput.action] || null;\n\n// ============================================\n// CLEAR CONTEXT\n// ============================================\n\nllmOutput.clear_booking_context =\n\tllmOutput.clear_booking_context || false;\n\n// ============================================\n// USER RESET OVERRIDE\n// ============================================\n\nif (\n\tinput.user_requested_reset &&\n\tllmOutput.action !== 'SHOW_MENU'\n) {\n\n\tconsole.log(\n\t\t'[USER_RESET_OVERRIDE] Forcing SHOW_MENU'\n\t);\n\n\tllmOutput.action = 'SHOW_MENU';\n\n\tllmOutput.intent = 'MENU_REQUEST';\n\n\tllmOutput.reply_text =\n\t\t'🔄 Starting fresh! How can I help you today?';\n\n\tllmOutput.new_step_state = 'MENU';\n\n\tllmOutput.clear_booking_context = true;\n\n\tllmOutput.requires_sub_workflow = false;\n\n\tllmOutput.sub_workflow_name = null;\n}\n\n// ============================================\n// FINAL RETURN\n// ============================================\n\nreturn [\n\t{\n\t\tjson: {\n\n\t\t\t...input,\n\n\t\t\tllm_output: llmOutput,\n\n\t\t\tllm_valid: true,\n\n\t\t\tllm_parse_error: parseError,\n\n\t\t\taction: llmOutput.action,\n\n\t\t\tintent: llmOutput.intent,\n\n\t\t\treply_text: llmOutput.reply_text,\n\n\t\t\tnew_step_state:\n\t\t\t\tllmOutput.new_step_state,\n\n\t\t\tentities: llmOutput.entities,\n\n\t\t\trequires_sub_workflow:\n\t\t\t\tllmOutput.requires_sub_workflow,\n\n\t\t\tsub_workflow_name:\n\t\t\t\tllmOutput.sub_workflow_name,\n\n\t\t\tclear_booking_context:\n\t\t\t\tllmOutput.clear_booking_context,\n\n\t\t\tconfidence:\n\t\t\t\tllmOutput.confidence || 0.8\n\t\t}\n\t}\n];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -1184,
        288
      ],
      "id": "e3fa61a1-31af-447e-a9ba-875dcf52d523",
      "name": "Parse_Validate_LLM"
    },
    {
      "parameters": {
        "rules": {
          "values": [
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-ask-user",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "ASK_USER",
                    "operator": {
                      "type": "string",
                      "operation": "equals",
                      "name": "filter.operator.equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "ASK_USER"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-fetch-slots",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "FETCH_SLOTS",
                    "operator": {
                      "type": "string",
                      "operation": "equals",
                      "name": "filter.operator.equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "FETCH_SLOTS"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-execute-booking",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "EXECUTE_BOOKING",
                    "operator": {
                      "type": "string",
                      "operation": "equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "EXECUTE_BOOKING"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-execute-reschedule",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "EXECUTE_RESCHEDULE",
                    "operator": {
                      "type": "string",
                      "operation": "equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "EXECUTE_RESCHEDULE"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-execute-cancel",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "EXECUTE_CANCEL",
                    "operator": {
                      "type": "string",
                      "operation": "equals",
                      "name": "filter.operator.equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "EXECUTE_CANCEL"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-answer-faq",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "ANSWER_FAQ",
                    "operator": {
                      "type": "string",
                      "operation": "equals",
                      "name": "filter.operator.equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "ANSWER_FAQ"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-show-menu",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "SHOW_MENU",
                    "operator": {
                      "type": "string",
                      "operation": "equals",
                      "name": "filter.operator.equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "SHOW_MENU"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-escalate-human",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "ESCALATE_HUMAN",
                    "operator": {
                      "type": "string",
                      "operation": "equals",
                      "name": "filter.operator.equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "ESCALATE_HUMAN"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict",
                  "version": 3
                },
                "conditions": [
                  {
                    "id": "rule-reset-session",
                    "leftValue": "={{ $json.action }}",
                    "rightValue": "RESET_SESSION",
                    "operator": {
                      "type": "string",
                      "operation": "equals",
                      "name": "filter.operator.equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "RESET_SESSION"
            }
          ]
        },
        "options": {
          "fallbackOutput": "none"
        }
      },
      "type": "n8n-nodes-base.switch",
      "typeVersion": 3.4,
      "position": [
        -944,
        208
      ],
      "id": "7d914e22-0879-4754-908a-0f353cacfc03",
      "name": "Switch_Action_Router"
    },
    {
      "parameters": {
        "jsCode": "// ============================================\n// DIRECT RESPONSE BUILDER\n// Production-safe n8n Code Node\n// Handles:\n// ASK_USER\n// SHOW_MENU\n// RESET_SESSION\n// ANSWER_FAQ\n// ============================================\n\nconst input = $('Parse_Validate_LLM').first().json;\n\nconst action = input.action || 'ASK_USER';\n\nconst state = input.current_state || {};\n\nconst llmOutput = input.llm_output || {};\n\n// ============================================\n// INITIAL VALUES\n// ============================================\n\nlet reply =\n\tinput.reply_text ||\n\t'How can I help you?';\n\nlet newStep =\n\tinput.new_step_state ||\n\tstate.step ||\n\t'MENU';\n\nlet clearContext =\n\tinput.clear_booking_context || false;\n\n// ============================================\n// FORCE MENU RESPONSE\n// ============================================\n\nif (\n\taction === 'SHOW_MENU' ||\n\taction === 'RESET_SESSION'\n) {\n\n\treply = `🏥 *Main Menu*\n\n1️⃣ *Book* — Make a new appointment\n\n2️⃣ *Reschedule* — Change existing booking\n\n3️⃣ *Cancel* — Cancel your booking\n\n4️⃣ *View* — See your current booking\n\n5️⃣ *FAQ* — Ask questions\n\nReply with a number or tell me what you'd like to do.`;\n\n\tnewStep = 'MENU';\n\n\tclearContext = true;\n}\n\n// ============================================\n// BUILD STATE DELTA\n// ============================================\n\nconst stateDelta = {\n\n\tstep: newStep,\n\n\tintent: input.intent || null,\n\n\taction: action\n};\n\n// ============================================\n// CONTEXT RESET\n// ============================================\n\nif (clearContext) {\n\n\tstateDelta.context = {\n\n\t\tselected_doctor: null,\n\n\t\tselected_date: null,\n\n\t\tselected_slot: null,\n\n\t\tbooking_id: null,\n\n\t\tcalendar_event_id: null,\n\n\t\toriginal_booking_id: null,\n\n\t\toriginal_calendar_event_id: null,\n\n\t\tslot_options: [],\n\n\t\tlast_question: null,\n\n\t\tretry_count: 0\n\t};\n\n} else {\n\n\tstateDelta.context = {\n\n\t\t...(state.context || {}),\n\n\t\t...(llmOutput.preserve_context || {})\n\t};\n}\n\n// ============================================\n// FINAL RESPONSE\n// ============================================\n\nreturn [\n\t{\n\t\tjson: {\n\n\t\t\tchat_id: input.chat_id,\n\n\t\t\treply_text: reply,\n\n\t\t\tstate_delta: stateDelta,\n\n\t\t\tcurrent_state: state,\n\n\t\t\tmessage_id: input.message_id,\n\n\t\t\tskip_subworkflow: true,\n\n\t\t\taction: action,\n\n\t\t\trequires_sub_workflow: false,\n\n\t\t\tsource: 'direct_response'\n\t\t}\n\t}\n];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -448,
        -96
      ],
      "id": "f7057fb9-3a18-43c7-ab3e-925fa7a85424",
      "name": "Direct_Response_Builder"
    },
    {
      "parameters": {
        "workflowId": {
          "__rl": true,
          "value": "=#wPpYVIcadO0gZeCa",
          "mode": "id",
          "cachedResultUrl": "/workflow/=%23wPpYVIcadO0gZeCa"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.executeWorkflow",
      "typeVersion": 1.1,
      "position": [
        -448,
        112
      ],
      "id": "41b93e77-a546-4635-b479-32de309d9c3b",
      "name": "Execute_BOOK_SPOKE"
    },
    {
      "parameters": {
        "workflowId": {
          "__rl": true,
          "value": "hrqwRqrdNAPBQZ8R",
          "mode": "list",
          "cachedResultUrl": "/workflow/hrqwRqrdNAPBQZ8R",
          "cachedResultName": "RESCHEDULE_SPOKE"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.executeWorkflow",
      "typeVersion": 1.1,
      "position": [
        -448,
        304
      ],
      "id": "40b3694b-12f7-47ff-bd58-363441978caa",
      "name": "Execute_RESCHEDULE_SPOKE"
    },
    {
      "parameters": {
        "workflowId": {
          "__rl": true,
          "value": "hErtBXBzdwcPADKK",
          "mode": "list",
          "cachedResultUrl": "/workflow/hErtBXBzdwcPADKK",
          "cachedResultName": "CANCEL_SPOKE"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.executeWorkflow",
      "typeVersion": 1.1,
      "position": [
        -448,
        512
      ],
      "id": "59d690d1-0137-4396-ad93-85fa6106d1f0",
      "name": "Execute_CANCEL_SPOKE"
    },
    {
      "parameters": {
        "workflowId": {
          "__rl": true,
          "value": "blPNEkC6RtYPVFkB",
          "mode": "list",
          "cachedResultUrl": "/workflow/blPNEkC6RtYPVFkB",
          "cachedResultName": "FAQ_SPOKE"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.executeWorkflow",
      "typeVersion": 1.1,
      "position": [
        -448,
        704
      ],
      "id": "4ea23226-aecc-4414-8ab0-ffa88b7d2086",
      "name": "Execute_FAQ_SPOKE"
    },
    {
      "parameters": {
        "options": {}
      },
      "type": "n8n-nodes-base.executeWorkflow",
      "typeVersion": 1.1,
      "position": [
        -448,
        912
      ],
      "id": "c1243ee3-4282-4bc9-a4e0-e4610cf3abd6",
      "name": "Execute_HUMAN_SPOKE",
      "disabled": true
    },
    {
      "parameters": {
        "jsCode": "// ============================================\n// FINAL STATE MERGE\n// Production-safe deep merge\n// ============================================\n\nconst input = $input.first().json;\n\n// ============================================\n// SAFE DEFAULTS\n// ============================================\n\nconst currentState = input.current_state || {};\n\nconst stateDelta = input.state_delta || {};\n\nconst llmOutput = input.llm_output || {};\n\nconst currentContext = currentState.context || {};\n\nconst currentMeta = currentState.meta || {};\n\n// ============================================\n// DEEP MERGE\n// ============================================\n\nconst mergedState = {\n\n\t...currentState,\n\n\t...stateDelta,\n\n\tcontext: {\n\n\t\t...currentContext,\n\n\t\t...(stateDelta.context || {})\n\t},\n\n\tmeta: {\n\n\t\t...currentMeta,\n\n\t\tlast_updated: new Date().toISOString(),\n\n\t\tlast_activity_ts: Date.now(),\n\n\t\tlock_version:\n\t\t\t(currentMeta.lock_version || 0) + 1\n\t}\n};\n\n// ============================================\n// CONVERSATION HISTORY\n// ============================================\n\nmergedState.context.conversation_history = [\n\n\t...(mergedState.context.conversation_history || []),\n\n\t{\n\t\trole: 'assistant',\n\n\t\tcontent:\n\t\t\tinput.reply_text ||\n\t\t\t'',\n\n\t\ttimestamp:\n\t\t\tnew Date().toISOString()\n\t}\n\n].slice(-20);\n\n// ============================================\n// FINAL RETURN\n// ============================================\n\nreturn [\n\t{\n\t\tjson: {\n\n\t\t\tchat_id: input.chat_id,\n\n\t\t\treply_text:\n\t\t\t\tinput.reply_text,\n\n\t\t\tfinal_state:\n\t\t\t\tmergedState,\n\n\t\t\tmessage_id:\n\t\t\t\tinput.message_id,\n\n\t\t\taction:\n\t\t\t\tinput.action,\n\n\t\t\tsource:\n\t\t\t\tinput.source ||\n\t\t\t\t'unknown'\n\t\t}\n\t}\n];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        240,
        256
      ],
      "id": "bbf4d950-d675-4d5c-b113-0e34f161bde8",
      "name": "Final_State_Merge"
    },
    {
      "parameters": {
        "operation": "set",
        "key": "={{ 'telegram:session:' + $json.chat_id }}",
        "value": "={{ JSON.stringify($json.final_state) }}",
        "expire": true,
        "ttl": 86400
      },
      "type": "n8n-nodes-base.redis",
      "typeVersion": 1,
      "position": [
        768,
        256
      ],
      "id": "b9975a3d-af5e-4419-bf9c-afa5f9d148e4",
      "name": "Redis_Save_State",
      "credentials": {
        "redis": {
          "id": "IFmfKowHmcx4QSHk",
          "name": "Redis account"
        }
      }
    },
    {
      "parameters": {
        "chatId": "={{ $('Telegram Bot').item.json.message.from.id }}",
        "text": "={{ $json.reply_text }}",
        "additionalFields": {
          "parse_mode": "Markdown"
        }
      },
      "type": "n8n-nodes-base.telegram",
      "typeVersion": 1.1,
      "position": [
        1152,
        256
      ],
      "id": "5ddb8a40-b84a-4895-ac62-122a24fa55c6",
      "name": "Telegram_Send_Reply",
      "webhookId": "5044e3a7-3b93-4114-9ab6-0312a6f761e5",
      "credentials": {
        "telegramApi": {
          "id": "XWY8EyYqQXb9Aj1W",
          "name": "Telegram account"
        }
      }
    },
    {
      "parameters": {
        "operation": "update",
        "documentId": {
          "__rl": true,
          "value": "={{ $env.GOOGLE_SHEETS_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "Patient_Details",
          "mode": "name"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "Telegram Chat ID": "={{ $json.chat_id }}",
            "Patient Name": "={{ $json.final_state.username }}",
            "Telegram Handle": "={{ $json.final_state.username ? '@' + $json.final_state.username : '' }}",
            "Patient Phone": "={{ $json.final_state.context.patient_phone || '' }}",
            "Last Interaction Date": "={{ $json.final_state.meta.last_updated }}",
            "Active Bookings": "={{ $json.final_state.step === 'CONFIRMED' && $json.final_state.intent === 'BOOK' ? 1 : ($json.final_state.step === 'MENU' && $json.final_state.intent === 'CANCEL' ? 0 : '') }}",
            "Total Bookings Count": "={{ $json.final_state.meta.total_bookings || 0 }}",
            "Total Reschedules Count": "={{ $json.final_state.meta.total_reschedules || 0 }}",
            "Total Cancellations Count": "={{ $json.final_state.meta.total_cancels || 0 }}",
            "Customer Segment": "={{ ($json.final_state.meta.total_bookings || 0) >= 3 ? 'LOYAL' : (($json.final_state.meta.total_bookings || 0) >= 1 ? 'ACTIVE' : 'POTENTIAL') }}"
          },
          "matchingColumns": [
            "Telegram Chat ID"
          ],
          "schema": []
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        464,
        256
      ],
      "id": "cbd171af-1772-4da7-b840-5eabb1d8761d",
      "name": "Sync_Patient_CRM",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    }
  ],
  "pinData": {},
  "connections": {
    "Telegram Bot": {
      "main": [
        [
          {
            "node": "Extract_Validate_Payload",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Extract_Validate_Payload": {
      "main": [
        [
          {
            "node": "Redis_Get_Session",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Redis_Get_Session": {
      "main": [
        [
          {
            "node": "Init_Parse_State",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Init_Parse_State": {
      "main": [
        [
          {
            "node": "Build_LLM_Context",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Build_LLM_Context": {
      "main": [
        [
          {
            "node": "Gemini_Router",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Google Gemini Chat Model": {
      "ai_languageModel": [
        [
          {
            "node": "Gemini_Router",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Gemini_Router": {
      "main": [
        [
          {
            "node": "Parse_Validate_LLM",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Parse_Validate_LLM": {
      "main": [
        [
          {
            "node": "Switch_Action_Router",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Switch_Action_Router": {
      "main": [
        [
          {
            "node": "Direct_Response_Builder",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Execute_BOOK_SPOKE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Execute_BOOK_SPOKE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Execute_RESCHEDULE_SPOKE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Execute_CANCEL_SPOKE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Execute_FAQ_SPOKE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Direct_Response_Builder",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Execute_HUMAN_SPOKE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Direct_Response_Builder",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Direct_Response_Builder": {
      "main": [
        [
          {
            "node": "Final_State_Merge",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Execute_BOOK_SPOKE": {
      "main": [
        [
          {
            "node": "Final_State_Merge",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Final_State_Merge": {
      "main": [
        [
          {
            "node": "Sync_Patient_CRM",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Redis_Save_State": {
      "main": [
        [
          {
            "node": "Telegram_Send_Reply",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Execute_RESCHEDULE_SPOKE": {
      "main": [
        [
          {
            "node": "Final_State_Merge",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Execute_CANCEL_SPOKE": {
      "main": [
        [
          {
            "node": "Final_State_Merge",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Execute_FAQ_SPOKE": {
      "main": [
        [
          {
            "node": "Final_State_Merge",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Execute_HUMAN_SPOKE": {
      "main": [
        [
          {
            "node": "Final_State_Merge",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Sync_Patient_CRM": {
      "main": [
        [
          {
            "node": "Redis_Save_State",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "active": false,
  "settings": {
    "executionOrder": "v1",
    "binaryMode": "separate"
  },
  "versionId": "b66d6ba6-3b6d-41c7-b5b7-84175c93ddc6",
  "meta": {
    "instanceId": "c5674022872009769c8b83e3189e707e15b254c1b9e48d6b8e871f168c7daed1"
  },
  "id": "TsL9vteP7VyXtxV6",
  "tags": []
}
``


### new_BOOK_SPOKE.json

``json
{
  "name": "new_BOOK_SPOKE",
  "nodes": [
    {
      "parameters": {
        "inputSource": "passthrough"
      },
      "type": "n8n-nodes-base.executeWorkflowTrigger",
      "typeVersion": 1.1,
      "position": [
        -1280,
        160
      ],
      "id": "6d379428-b0c4-486b-9237-94a546640268",
      "name": "When_Executed"
    },
    {
      "parameters": {
        "jsCode": "// Parse input from parent workflow\nconst input = $input.first().json;\nconst parentData = input.workflowData ? JSON.parse(input.workflowData) : input;\n\nreturn [{\n    json: {\n        chat_id: parentData.chat_id,\n        user_id: parentData.user_id,\n        username: parentData.username,\n        message_text: parentData.message_text,\n        message_id: parentData.message_id,\n        current_state: parentData.current_state,\n        entities: parentData.entities || {},\n        llm_output: parentData.llm_output || {},\n        action: parentData.action,\n        intent: parentData.intent,\n        reply_text: parentData.reply_text,\n        new_step_state: parentData.new_step_state,\n        system_time: parentData.system_time\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -880,
        160
      ],
      "id": "16169b09-e062-46d4-a79a-af8e994b05e6",
      "name": "Parse_Parent_Input"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst entities = input.entities || {};\nconst state = input.current_state || {};\n\n// Check if we have doctor and date\nconst hasDoctor = entities.doctor && entities.doctor.trim().length > 0;\nconst hasDate = entities.date && entities.date.match(/^\\d{4}-\\d{2}-\\d{2}$/);\n\n// Check patient details if OTHERS\nconst bookingType = entities.booking_type || state.context.booking_type || 'SELF';\nconst hasPatientName = bookingType === 'SELF' || (entities.patient_name && entities.patient_name.trim().length > 0) || (state.context.patient_name && state.context.patient_name.trim().length > 0);\nconst hasPatientPhone = bookingType === 'SELF' || (entities.patient_phone && entities.patient_phone.trim().length > 0) || (state.context.patient_phone && state.context.patient_phone.trim().length > 0);\n\nif (!hasDoctor || !hasDate || !hasPatientName || !hasPatientPhone) {\n    // Missing info - ask user conversationally (Clara receptionist voice)\n    let reply = \"\";\n    let nextStep = \"MENU\";\n    \n    if (!hasDoctor || !hasDate) {\n        reply = `Hello ${state.username || 'there'}! I'd be absolutely delighted to help you schedule a visit today. To get started, could you please share:\\n\\n`;\n        if (!hasDoctor) {\n            reply += `👨‍⚕️ *Which doctor* you would like to see? (Dr. Smith - Cardiology, Dr. Jones - Dermatology, or Dr. Lee - General Medicine)\\n`;\n            nextStep = \"AWAITING_DOCTOR\";\n        }\n        if (!hasDate) {\n            reply += `📅 *Which date* works best for your schedule? (e.g. tomorrow, next Monday, or a specific date like 2026-05-20)\\n`;\n            if (hasDoctor) nextStep = \"AWAITING_DATE\";\n        }\n    } else if (!hasPatientName || !hasPatientPhone) {\n        reply = `👨‍👩‍👧‍👦 I see you are scheduling this appointment on behalf of someone else! I'd be happy to set that up. To compile their clinical registration card, could you please tell me:\\n\\n`;\n        if (!hasPatientName) {\n            reply += `👤 The patient's *Full Name*?\\n`;\n            nextStep = \"AWAITING_PATIENT_DETAILS\";\n        }\n        if (!hasPatientPhone) {\n            reply += `📞 The patient's *Contact Phone Number*?\\n`;\n            if (hasPatientName) nextStep = \"AWAITING_PATIENT_DETAILS\";\n        }\n    }\n\n    return [{\n        json: {\n            chat_id: input.chat_id,\n            reply_text: reply,\n            state_delta: {\n                step: nextStep,\n                intent: \"BOOK\",\n                action: \"ASK_USER\",\n                context: {\n                    ...state.context,\n                    selected_doctor: entities.doctor || state.context.selected_doctor,\n                    selected_date: entities.date || state.context.selected_date,\n                    booking_type: bookingType,\n                    patient_name: entities.patient_name || state.context.patient_name,\n                    patient_phone: entities.patient_phone || state.context.patient_phone\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"book_spoke_ask\"\n        }\n    }];\n}\n\n// We have all details - proceed\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        doctor: entities.doctor || state.context.selected_doctor,\n        date: entities.date || state.context.selected_date,\n        booking_type: bookingType,\n        patient_name: entities.patient_name || state.context.patient_name || (state.username || state.first_name || 'Patient'),\n        patient_phone: entities.patient_phone || state.context.patient_phone || input.chat_id,\n        current_state: state,\n        message_id: input.message_id,\n        proceed_to_fetch: true\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -352,
        576
      ],
      "id": "4ead4cb8-0cac-43c4-acd5-9a13bc512295",
      "name": "Check_Required_Entities"
    },
    {
      "parameters": {
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        464,
        560
      ],
      "id": "f32d3202-9963-4ce2-9c72-623a4069d276",
      "name": "Fetch_Slots_From_Sheets",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "const input = $('Check_Required_Entities').first().json;\nconst schedules = $('Fetch_Schedules').all().map(item => item.json);\nconst availability = $('Fetch_Slots_From_Sheets').all().map(item => item.json);\nconst doctor = input.doctor;\nconst date = input.date;\nconst state = input.current_state;\nconst chat_id = input.chat_id;\nconst username = state.username || '';\n\n// 1. Scan Booking DB for duplicate active bookings (Self-Healing database-level lock check)\nconst existingBooking = availability.find(row => {\n    const rowStatus = row['Status'] || row['status'] || '';\n    const rowPhone = row['Patient Phone'] || row['patient_phone'] || '';\n    return rowStatus.toUpperCase() === 'BOOKED' && \n           (rowPhone.includes(String(chat_id)) || (username && rowPhone.includes(username)));\n});\n\nif (existingBooking) {\n    const bDoc = existingBooking['Doctor'] || existingBooking['doctor'];\n    const bDate = existingBooking['Date'] || existingBooking['date'];\n    const bSlot = existingBooking['Time Slot'] || existingBooking['time_slot'];\n    const bId = existingBooking['Booking ID'] || existingBooking['booking_id'];\n    const bCal = existingBooking['Calendar Event ID'] || existingBooking['calendar_event_id'];\n\n    return [{\n        json: {\n            chat_id: chat_id,\n            reply_text: `⚠️ *Duplicate Booking Prevented*\\n\\nOh! I see you already have an active appointment scheduled, ${state.username || 'there'}:\\n\\n👨‍⚕️ *Doctor*: ${bDoc}\\n📅 *Date*: ${bDate}\\n⏰ *Time*: ${bSlot}\\n\\nLife gets busy, but you can easily reschedule this appointment using *reschedule* or cancel it using *cancel* before booking a new one!`,\n            state_delta: {\n                step: \"MENU\",\n                intent: \"BOOK\",\n                action: \"ASK_USER\",\n                context: {\n                    ...state.context,\n                    booking_id: bId,\n                    calendar_event_id: bCal,\n                    selected_doctor: bDoc,\n                    selected_date: bDate,\n                    selected_slot: bSlot\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"book_duplicate_prevented\"\n        }\n    }];\n}\n\n// 2. Timezone-safe day of week calculation\nconst [year, month, day] = date.split('-').map(Number);\nconst dateObj = new Date(year, month - 1, day);\nconst days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];\nconst dayOfWeek = days[dateObj.getDay()];\n\n// 3. Find doctor shift schedule in Doctor_Schedules\nconst shift = schedules.find(s => \n    (s['Doctor'] || s['doctor'] || '').toLowerCase() === doctor.toLowerCase() && \n    ((s['Day of Week'] || s['day_of_week'] || '') === dayOfWeek || (s['Day of Week'] || s['day_of_week'] || '') === 'All')\n);\n\nif (!shift) {\n    return [{\n        json: {\n            chat_id: chat_id,\n            reply_text: `❌ Oh, I'm so sorry! Dr. ${doctor} does not have any shifts scheduled on ${date} (${dayOfWeek}).\\n\\nPlease select another date for Dr. ${doctor}, or say 'menu' to see our other specialists!`,\n            state_delta: {\n                step: \"AWAITING_DATE\",\n                intent: \"BOOK\",\n                action: \"ASK_USER\",\n                context: {\n                    ...state.context,\n                    selected_doctor: doctor,\n                    selected_date: null\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"book_no_doctor_shift\"\n        }\n    }];\n}\n\n// 4. Dynamically generate slot blocks\nconst generatedSlots = [];\nconst startTime = shift['Start Time'] || shift['start_time'] || '09:00';\nconst endTime = shift['End Time'] || shift['end_time'] || '17:00';\nconst duration = parseInt(shift['Slot Duration'] || shift['slot_duration'] || 60);\n\nlet [currH, currM] = startTime.split(':').map(Number);\nconst [endH, endM] = endTime.split(':').map(Number);\n\nwhile ((currH * 60 + currM) + duration <= (endH * 60 + endM)) {\n    const nextTotal = (currH * 60 + currM) + duration;\n    const nextH = Math.floor(nextTotal / 60);\n    const nextM = nextTotal % 60;\n    \n    const startStr = `${String(currH).padStart(2, '0')}:${String(currM).padStart(2, '0')}`;\n    const endStr = `${String(nextH).padStart(2, '0')}:${String(nextM).padStart(2, '0')}`;\n    \n    generatedSlots.push(`${startStr}-${endStr}`);\n    currH = nextH;\n    currM = nextM;\n}\n\n// 5. Exclude slots that are already BOOKED or PENDING in Availability\nconst bookedSlots = availability.filter(row => {\n    const rowDoctor = row['Doctor'] || row['doctor'] || '';\n    const rowDate = row['Date'] || row['date'] || '';\n    const rowStatus = row['Status'] || row['status'] || '';\n    return rowDoctor.toLowerCase() === doctor.toLowerCase() && \n           rowDate === date && \n           (rowStatus.toUpperCase() === 'BOOKED' || rowStatus.toUpperCase() === 'PENDING');\n});\n\nconst freeSlots = generatedSlots.filter(time => \n    !bookedSlots.some(b => (b['Time Slot'] || b['time_slot']) === time)\n);\n\nif (freeSlots.length === 0) {\n    return [{\n        json: {\n            chat_id: chat_id,\n            reply_text: `❌ Oh! It looks like Dr. ${doctor} is fully booked on ${date}.\\n\\nPlease try selecting a different date or another doctor, or say 'menu' to see options!`,\n            state_delta: {\n                step: \"MENU\",\n                intent: \"BOOK\",\n                action: \"ASK_USER\"\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"book_no_slots_free\"\n        }\n    }];\n}\n\n// 6. Format available slots\nconst formatted = freeSlots.map((time, index) => `${index + 1}. ${time}`).join('\\n');\nconst slotOptions = freeSlots.map(time => ({\n    time_slot: time,\n    row_index: null, // Signals dynamic append\n    doctor: doctor,\n    date: date,\n    version: 0\n}));\n\nreturn [{\n    json: {\n        chat_id: chat_id,\n        reply_text: `🩺 *Select Appointment Slot*\\n\\nHere are the available timings for *Dr. ${doctor}* on *${date}*:\\n\\n${formatted}\\n\\nReply with a number (1-${freeSlots.length}) to pick your slot.`,\n        state_delta: {\n            step: \"AWAITING_SLOT_CONFIRM\",\n            intent: \"BOOK\",\n            action: \"FETCH_SLOTS\",\n            context: {\n                ...state.context,\n                selected_doctor: doctor,\n                selected_date: date,\n                booking_type: input.booking_type,\n                patient_name: input.patient_name,\n                patient_phone: input.patient_phone,\n                slot_options: slotOptions\n            }\n        },\n        current_state: state,\n        slot_data: slotOptions,\n        requires_sub_workflow: false,\n        source: \"book_slots_fetched\"\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        848,
        576
      ],
      "id": "66033724-c8a4-4241-b330-47438e4454ef",
      "name": "Filter_Format_Slots"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state;\nconst slotOptions = state.context.slot_options || [];\nconst messageText = input.message_text || '';\n\n// Try to parse slot index from message\nlet selectedIndex = parseInt(messageText.trim()) - 1;\nif (isNaN(selectedIndex) || selectedIndex < 0 || selectedIndex >= slotOptions.length) {\n    // Try to match by time string\n    const timeMatch = slotOptions.findIndex(opt => \n        messageText.includes(opt.time_slot)\n    );\n    if (timeMatch >= 0) selectedIndex = timeMatch;\n}\n\nif (selectedIndex < 0 || selectedIndex >= slotOptions.length) {\n    return [{\n        json: {\n            chat_id: input.chat_id,\n            reply_text: `⚠️ Invalid selection. Please reply with a number from 1 to ${slotOptions.length}.\n\nOr say *menu* to start over.`,\n            state_delta: {\n                step: \"AWAITING_SLOT_CONFIRM\",\n                intent: \"BOOK\",\n                action: \"ASK_USER\",\n                context: state.context\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"book_invalid_slot\"\n        }\n    }];\n}\n\nconst selectedSlot = slotOptions[selectedIndex];\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        selected_slot: selectedSlot,\n        slot_index: selectedIndex,\n        current_state: state,\n        message_id: input.message_id,\n        proceed_to_lock: true\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        400,
        160
      ],
      "id": "764f7101-0735-4c5b-900b-db0d51cb4900",
      "name": "Validate_Slot_Selection"
    },
    {
      "parameters": {
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        848,
        160
      ],
      "id": "12c49ffb-a164-476d-9633-5e50d8a71439",
      "name": "Read_Row_Version",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst allRows = $input.all()[0]?.json || [];\nconst selectedSlot = input.selected_slot;\nconst state = input.current_state;\n\n// Search sheet for existing active/pending booking for this slot\nconst targetRow = allRows.find(row => {\n    const rowDoctor = row['Doctor'] || row['doctor'] || '';\n    const rowDate = row['Date'] || row['date'] || '';\n    const rowTime = row['Time Slot'] || row['time_slot'] || '';\n    const rowStatus = row['Status'] || row['status'] || '';\n\n    return rowDoctor.toLowerCase() === selectedSlot.doctor.toLowerCase() && \n           rowDate === selectedSlot.date && \n           rowTime === selectedSlot.time_slot &&\n           (rowStatus.toUpperCase() === 'BOOKED' || rowStatus.toUpperCase() === 'PENDING');\n});\n\nif (targetRow) {\n    return [{\n        json: {\n            chat_id: input.chat_id,\n            reply_text: \"⚠️ Oh! That slot was just booked by someone else. Let me refresh availability...\",\n            state_delta: {\n                step: \"AWAITING_SLOT_CONFIRM\",\n                intent: \"BOOK\",\n                action: \"FETCH_SLOTS\",\n                context: {\n                    ...state.context,\n                    selected_slot: null,\n                    retry_count: (state.context.retry_count || 0) + 1\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            fallback_action: \"FETCH_SLOTS\",\n            source: \"book_race_lost\"\n        }\n    }];\n}\n\n// Slot is free - row_number is null to APPEND new PENDING row\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        selected_slot: selectedSlot,\n        row_number: null, // Signals APPEND\n        current_state: state,\n        message_id: input.message_id,\n        proceed_to_update: true\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1072,
        160
      ],
      "id": "07e9bfaa-b110-42ab-bb77-0a61fa078d6c",
      "name": "Verify_Lock_Slot"
    },
    {
      "parameters": {
        "operation": "append",
        "documentId": {
          "__rl": true,
          "value": "={{ $env.GOOGLE_SHEETS_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "={{ $env.GOOGLE_SHEET_AVAILABILITY }}",
          "mode": "name"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "Date": "={{ $json.selected_slot.date }}",
            "Doctor": "={{ $json.selected_slot.doctor }}",
            "Time Slot": "={{ $json.selected_slot.time_slot }}",
            "Status": "PENDING",
            "Booking ID": "={{ $json.current_state.context.idempotency_key }}",
            "Version": "1"
          },
          "schema": []
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        1360,
        160
      ],
      "id": "2131eb8b-a8e9-4d79-ada3-0a6bae471efa",
      "name": "Update_Sheet_Pending",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "calendar": {
          "__rl": true,
          "value": "2174f9a8fabdf573966591e3e2d8e606a068d48ee1ddbcdb2dad58fe70341800@group.calendar.google.com",
          "mode": "list",
          "cachedResultName": "Doctor Appointments"
        },
        "start": "={{ $json.selected_slot.date }}T{{ $json.selected_slot.time_slot.split('-')[0] }}:00",
        "end": "={{ $json.selected_slot.date }}T{{ $json.selected_slot.time_slot.split('-')[1] }}:00",
        "additionalFields": {
          "description": "={{ 'Patient: ' + $json.current_state.username + '\\nChat ID: ' + $json.chat_id + '\\nBooking via Telegram Bot' }}",
          "sendUpdates": "all",
          "summary": "={{ 'Appointment: ' + $json.current_state.username + ' with ' + $json.selected_slot.doctor }}"
        }
      },
      "type": "n8n-nodes-base.googleCalendar",
      "typeVersion": 1.3,
      "position": [
        1600,
        160
      ],
      "id": "8256a697-22b4-4793-a2ba-1262820ab83b",
      "name": "Create_Calendar_Event",
      "credentials": {
        "googleCalendarOAuth2Api": {
          "id": "7qrcSH511UKOGGlN",
          "name": "Google Calendar account"
        }
      }
    },
    {
      "parameters": {
        "operation": "update",
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "Status": "BOOKED",
            "Patient Phone": "={{ $json.patient_phone }}",
            "Calendar Event ID": "={{ $json.event_id }}",
            "Version": "1"
          },
          "matchingColumns": [
            "Booking ID"
          ],
          "schema": []
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        2048,
        160
      ],
      "id": "f1343996-82e1-448a-bd11-69d06efc4944",
      "name": "Update_Sheet_BOOKED",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state;\nconst slot = input.selected_slot;\n\nconst name = state.username || state.first_name || 'there';\nconst patientName = state.context.patient_name || name;\n\n// Increment total bookings in metadata\nstate.meta.total_bookings = (state.meta.total_bookings || 0) + 1;\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        reply_text: `🎉 *Wonderful News, ${name}!*\\n\\nI have successfully scheduled that appointment for you:\\n\\n👤 *Patient*: ${patientName}\\n👨‍⚕️ *Doctor*: ${slot.doctor}\\n📅 *Date*: ${slot.date}\\n⏰ *Time*: ${slot.time_slot}\\n\\nDr. ${slot.doctor} is looking forward to this visit! If anything comes up, feel free to reschedule or cancel at any time.\\n\\nSay *menu* to see other options or *view* to see your active details.`,\n        state_delta: {\n            step: \"CONFIRMED\",\n            intent: \"BOOK\",\n            action: \"EXECUTE_BOOKING\",\n            context: {\n                ...state.context,\n                selected_doctor: slot.doctor,\n                selected_date: slot.date,\n                selected_slot: slot.time_slot,\n                booking_id: input.booking_id,\n                calendar_event_id: input.event_id\n            }\n        },\n        current_state: state,\n        requires_sub_workflow: false,\n        source: \"book_confirmed\"\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        2288,
        144
      ],
      "id": "7ccf6fe5-8933-4093-a294-d63e3118ce54",
      "name": "Build_Success_Response"
    },
    {
      "parameters": {
        "jsCode": "// Error handler - rollback if calendar creation failed\nconst input = $input.first().json;\nconst state = input.current_state;\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        reply_text: \"❌ Sorry, there was an error processing your booking. Please try again or say *menu* to start over.\",\n        state_delta: {\n            step: \"MENU\",\n            intent: \"BOOK\",\n            action: \"ASK_USER\",\n            context: {\n                ...state.context,\n                selected_doctor: null,\n                selected_date: null,\n                selected_slot: null,\n                retry_count: (state.context.retry_count || 0) + 1\n            }\n        },\n        current_state: state,\n        requires_sub_workflow: false,\n        source: \"book_error\"\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1760,
        544
      ],
      "id": "8cc807ef-2eab-43c7-9375-9f43fb5f98a7",
      "name": "Error_Rollback"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "check-step",
              "leftValue": "={{ $json.current_state.step }}",
              "rightValue": "AWAITING_SLOT_CONFIRM",
              "operator": {
                "type": "string",
                "operation": "equals"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        -528,
        176
      ],
      "id": "4ad14b83-4405-4da0-9a31-2c571e89c911",
      "name": "Branch_Booking_Flow"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "check-proceed",
              "leftValue": "={{ $json.proceed_to_fetch }}",
              "rightValue": "true",
              "operator": {
                "type": "boolean",
                "operation": "true"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        -112,
        576
      ],
      "id": "5098e470-c3b6-4121-b9f2-24fd56766f59",
      "name": "Proceed_To_Fetch_Slots"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "check-proceed-lock",
              "leftValue": "={{ $json.proceed_to_lock }}",
              "rightValue": "true",
              "operator": {
                "type": "boolean",
                "operation": "true"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        624,
        192
      ],
      "id": "7d051dbe-6744-4d46-a2ac-df4232fe42cf",
      "name": "Selection_Is_Valid"
    },
    {
      "parameters": {
        "jsCode": "const calendarOutput = $('Create_Calendar_Event').first().json;\nconst lockSlotOutput = $('Verify_Lock_Slot').first().json;\nconst state = lockSlotOutput.current_state;\nconst context = state.context;\n\nconst bookingType = context.booking_type || 'SELF';\nlet patientDetails = \"\";\n\nif (bookingType === 'OTHERS') {\n    const parentName = state.username || state.first_name || 'Parent';\n    patientDetails = `Name: ${context.patient_name} | Phone: ${context.patient_phone} | Telegram: @${state.username || 'user'} (Parent) | Chat: ${lockSlotOutput.chat_id}`;\n} else {\n    const firstName = state.username || state.first_name || 'Patient';\n    const username = state.username ? ` (@${state.username})` : '';\n    patientDetails = `Name: ${firstName}${username} | Telegram Chat: ${lockSlotOutput.chat_id}`;\n}\n\nreturn [{\n    json: {\n        chat_id: lockSlotOutput.chat_id,\n        booking_id: lockSlotOutput.current_state.context.idempotency_key,\n        event_id: calendarOutput.id,\n        selected_slot: lockSlotOutput.selected_slot,\n        current_state: lockSlotOutput.current_state,\n        patient_phone: patientDetails\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1840,
        160
      ],
      "id": "e9a02201-95b2-4a2e-85c5-400e39d46d34",
      "name": "Prepare_Booked_Data"
    },
    {
      "parameters": {
        "documentId": {
          "__rl": true,
          "value": "={{ $env.GOOGLE_SHEETS_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "Doctor_Schedules",
          "mode": "name"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        160,
        560
      ],
      "id": "e9fbdb65-e255-4295-974a-e43380b7226d",
      "name": "Fetch_Schedules",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    }
  ],
  "pinData": {},
  "connections": {
    "When_Executed": {
      "main": [
        [
          {
            "node": "Parse_Parent_Input",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Parse_Parent_Input": {
      "main": [
        [
          {
            "node": "Branch_Booking_Flow",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Check_Required_Entities": {
      "main": [
        [
          {
            "node": "Proceed_To_Fetch_Slots",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Fetch_Slots_From_Sheets": {
      "main": [
        [
          {
            "node": "Filter_Format_Slots",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Validate_Slot_Selection": {
      "main": [
        [
          {
            "node": "Selection_Is_Valid",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Read_Row_Version": {
      "main": [
        [
          {
            "node": "Verify_Lock_Slot",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Verify_Lock_Slot": {
      "main": [
        [
          {
            "node": "Update_Sheet_Pending",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Update_Sheet_Pending": {
      "main": [
        [
          {
            "node": "Create_Calendar_Event",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Create_Calendar_Event": {
      "main": [
        [
          {
            "node": "Prepare_Booked_Data",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Update_Sheet_BOOKED": {
      "main": [
        [
          {
            "node": "Build_Success_Response",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Branch_Booking_Flow": {
      "main": [
        [
          {
            "node": "Validate_Slot_Selection",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Check_Required_Entities",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Proceed_To_Fetch_Slots": {
      "main": [
        [
          {
            "node": "Fetch_Schedules",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Selection_Is_Valid": {
      "main": [
        [
          {
            "node": "Read_Row_Version",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Prepare_Booked_Data": {
      "main": [
        [
          {
            "node": "Update_Sheet_BOOKED",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Fetch_Schedules": {
      "main": [
        [
          {
            "node": "Fetch_Slots_From_Sheets",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "active": false,
  "settings": {
    "executionOrder": "v1",
    "binaryMode": "separate"
  },
  "versionId": "e264dd18-e7ec-459a-9f39-6a2a3e68eff4",
  "meta": {
    "instanceId": "c5674022872009769c8b83e3189e707e15b254c1b9e48d6b8e871f168c7daed1"
  },
  "id": "Y5SgpRGyNLif8HzR",
  "tags": []
}
``


### NEW_RESCHEDULE_SPOKE.json

``json
{
  "name": "NEW_RESCHEDULE_SPOKE",
  "nodes": [
    {
      "parameters": {
        "inputSource": "passthrough"
      },
      "type": "n8n-nodes-base.executeWorkflowTrigger",
      "typeVersion": 1.1,
      "position": [
        -1024,
        64
      ],
      "id": "aaa25359-36ca-4f27-b785-6523a9b5f6e7",
      "name": "When_Executed"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst parentData = input.workflowData ? JSON.parse(input.workflowData) : input;\n\nreturn [{\n    json: {\n        chat_id: parentData.chat_id,\n        user_id: parentData.user_id,\n        username: parentData.username,\n        message_text: parentData.message_text,\n        message_id: parentData.message_id,\n        current_state: parentData.current_state,\n        entities: parentData.entities || {},\n        llm_output: parentData.llm_output || {},\n        action: parentData.action,\n        intent: parentData.intent,\n        reply_text: parentData.reply_text,\n        new_step_state: parentData.new_step_state,\n        system_time: parentData.system_time\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -640,
        64
      ],
      "id": "9a97f194-fd27-493b-a9e5-3e363cd3e3aa",
      "name": "Parse_Parent_Input"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state;\nconst chatId = input.chat_id;\n\n// We proceed to sheets anyway to check database (Self-Healing)\nreturn [{\n    json: {\n        chat_id: chatId,\n        booking_id: state.context.booking_id || null,\n        calendar_event_id: state.context.calendar_event_id || null,\n        current_booking: {\n            doctor: state.context.selected_doctor || null,\n            date: state.context.selected_date || null,\n            slot: state.context.selected_slot || null\n        },\n        current_state: state,\n        message_id: input.message_id,\n        proceed_to_fetch: true\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -192,
        -240
      ],
      "id": "fecd5ecd-c5ea-489e-b033-d882f2807837",
      "name": "Lookup_Existing_Booking"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst schedules = $('Fetch_Schedules').all().map(item => item.json);\nconst availability = $('Get row(s) in sheet').all().map(item => item.json);\nconst entities = input.entities || {};\nconst state = input.current_state || {};\nconst chat_id = input.chat_id;\nconst username = state.username || '';\n\nlet oldBooking = input.current_booking || {};\nlet bookingId = input.booking_id;\nlet calendarEventId = input.calendar_event_id;\n\n// 1. Scan Sheets DB for active booking if session was lost (Self-Healing)\nif (!bookingId) {\n    const dbBooking = availability.find(row => {\n        const rowStatus = row['Status'] || row['status'] || '';\n        const rowPhone = row['Patient Phone'] || row['patient_phone'] || '';\n        return rowStatus.toUpperCase() === 'BOOKED' && \n               (rowPhone.includes(String(chat_id)) || (username && rowPhone.includes(username)));\n    });\n\n    if (!dbBooking) {\n        return [{\n            json: {\n                chat_id: chat_id,\n                reply_text: `❌ Oh! It looks like you don't have any active appointments scheduled with us, ${state.username || 'there'}.\\n\\nWould you like to *book* a new appointment instead?`,\n                state_delta: {\n                    step: \"MENU\",\n                    intent: \"RESCHEDULE\",\n                    action: \"ASK_USER\"\n                },\n                current_state: state,\n                requires_sub_workflow: false,\n                source: \"res_no_booking\"\n            }\n        }];\n    }\n\n    bookingId = dbBooking['Booking ID'] || dbBooking['booking_id'];\n    calendarEventId = dbBooking['Calendar Event ID'] || dbBooking['calendar_event_id'];\n    oldBooking = {\n        doctor: dbBooking['Doctor'] || dbBooking['doctor'],\n        date: dbBooking['Date'] || dbBooking['date'],\n        slot: dbBooking['Time Slot'] || dbBooking['time_slot']\n    };\n}\n\nconst newDate = entities.reschedule_target_date || entities.date;\nconst doctor = entities.doctor || oldBooking.doctor;\n\nif (!newDate) {\n    return [{\n        json: {\n            chat_id: input.chat_id,\n            reply_text: `📅 *Select Reschedule Date*\\n\\nI'd be happy to help you change your appointment with Dr. ${oldBooking.doctor}, ${state.username || 'there'}.\\n\\nWhich *new date* would you prefer? (e.g. tomorrow, next Monday, or a specific date like 2026-05-25)`,\n            state_delta: {\n                step: \"AWAITING_RESCHEDULE_DATE\",\n                intent: \"RESCHEDULE\",\n                action: \"ASK_USER\",\n                context: {\n                    ...state.context,\n                    booking_id: bookingId,\n                    calendar_event_id: calendarEventId,\n                    selected_doctor: oldBooking.doctor,\n                    selected_date: oldBooking.date,\n                    selected_slot: oldBooking.slot\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"res_ask_date\"\n        }\n    }];\n}\n\n// 2. Timezone-safe day of week calculation\nconst [year, month, day] = newDate.split('-').map(Number);\nconst dateObj = new Date(year, month - 1, day);\nconst days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];\nconst dayOfWeek = days[dateObj.getDay()];\n\n// 3. Find doctor shift schedule in Doctor_Schedules\nconst shift = schedules.find(s => \n    (s['Doctor'] || s['doctor'] || '').toLowerCase() === doctor.toLowerCase() && \n    ((s['Day of Week'] || s['day_of_week'] || '') === dayOfWeek || (s['Day of Week'] || s['day_of_week'] || '') === 'All')\n);\n\nif (!shift) {\n    return [{\n        json: {\n            chat_id: chat_id,\n            reply_text: `❌ Oh! Dr. ${doctor} does not have any shifts scheduled on ${newDate} (${dayOfWeek}).\\n\\nPlease select another date for Dr. ${doctor}, or say 'menu' to start over!`,\n            state_delta: {\n                step: \"AWAITING_RESCHEDULE_DATE\",\n                intent: \"RESCHEDULE\",\n                action: \"ASK_USER\",\n                context: {\n                    ...state.context,\n                    booking_id: bookingId,\n                    calendar_event_id: calendarEventId,\n                    selected_doctor: oldBooking.doctor,\n                    selected_date: oldBooking.date,\n                    selected_slot: oldBooking.slot\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"res_no_doctor_shift\"\n        }\n    }];\n}\n\n// 4. Dynamically generate slot blocks\nconst generatedSlots = [];\nconst startTime = shift['Start Time'] || shift['start_time'] || '09:00';\nconst endTime = shift['End Time'] || shift['end_time'] || '17:00';\nconst duration = parseInt(shift['Slot Duration'] || shift['slot_duration'] || 60);\n\nlet [currH, currM] = startTime.split(':').map(Number);\nconst [endH, endM] = endTime.split(':').map(Number);\n\nwhile ((currH * 60 + currM) + duration <= (endH * 60 + endM)) {\n    const nextTotal = (currH * 60 + currM) + duration;\n    const nextH = Math.floor(nextTotal / 60);\n    const nextM = nextTotal % 60;\n    \n    const startStr = `${String(currH).padStart(2, '0')}:${String(currM).padStart(2, '0')}`;\n    const endStr = `${String(nextH).padStart(2, '0')}:${String(nextM).padStart(2, '0')}`;\n    \n    generatedSlots.push(`${startStr}-${endStr}`);\n    currH = nextH;\n    currM = nextM;\n}\n\n// 5. Exclude slots that are already BOOKED or PENDING in Availability\nconst bookedSlots = availability.filter(row => {\n    const rowDoctor = row['Doctor'] || row['doctor'] || '';\n    const rowDate = row['Date'] || row['date'] || '';\n    const rowStatus = row['Status'] || row['status'] || '';\n    return rowDoctor.toLowerCase() === doctor.toLowerCase() && \n           rowDate === newDate && \n           (rowStatus.toUpperCase() === 'BOOKED' || rowStatus.toUpperCase() === 'PENDING');\n});\n\nconst freeSlots = generatedSlots.filter(time => \n    !bookedSlots.some(b => (b['Time Slot'] || b['time_slot']) === time)\n);\n\nif (freeSlots.length === 0) {\n    return [{\n        json: {\n            chat_id: chat_id,\n            reply_text: `❌ Oh, I'm sorry! Dr. ${doctor} is fully booked on ${newDate}.\\n\\nPlease try a different date or select another doctor!`,\n            state_delta: {\n                step: \"AWAITING_RESCHEDULE_DATE\",\n                intent: \"RESCHEDULE\",\n                action: \"ASK_USER\",\n                context: {\n                    ...state.context,\n                    booking_id: bookingId,\n                    calendar_event_id: calendarEventId,\n                    selected_doctor: oldBooking.doctor,\n                    selected_date: oldBooking.date,\n                    selected_slot: oldBooking.slot\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"res_no_slots_free\"\n        }\n    }];\n}\n\nconst formatted = freeSlots.map((time, index) => `${index + 1}. ${time}`).join('\\n');\nconst slotOptions = freeSlots.map(time => ({\n    time_slot: time,\n    row_index: null, // Dynamic slot append\n    doctor: doctor,\n    date: newDate,\n    version: 0\n}));\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        reply_text: `📅 *Select New Timing Slot*\\n\\nHere are the available timings for *Dr. ${doctor}* on *${newDate}*:\\n\\n${formatted}\\n\\nReply with the number to confirm your rescheduling.`,\n        state_delta: {\n            step: \"AWAITING_RESCHEDULE_SLOT\",\n            intent: \"RESCHEDULE\",\n            action: \"FETCH_SLOTS\",\n            context: {\n                ...state.context,\n                booking_id: bookingId,\n                calendar_event_id: calendarEventId,\n                selected_doctor: oldBooking.doctor,\n                selected_date: oldBooking.date,\n                selected_slot: oldBooking.slot,\n                slot_options: slotOptions,\n                reschedule_target_date: newDate\n            }\n        },\n        current_state: state,\n        new_slot_options: slotOptions,\n        requires_sub_workflow: false,\n        source: \"res_slots_fetched\"\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1136,
        -256
      ],
      "id": "03ce99b1-a427-449a-8392-7a1e83683126",
      "name": "Filter_Format_New_Slots"
    },
    {
      "parameters": {
        "operation": "append",
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "Date": "={{ $json.new_slot.date }}",
            "Doctor": "={{ $json.new_slot.doctor }}",
            "Time Slot": "={{ $json.new_slot.time_slot }}",
            "Status": "PENDING",
            "Booking ID": "={{ $json.current_state.context.idempotency_key }}",
            "Version": "1"
          },
          "schema": []
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        752,
        112
      ],
      "id": "f1885c5f-797c-4082-b456-978ad917a9d1",
      "name": "Lock_NEW_Slot",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        992,
        96
      ],
      "id": "0cecdfd2-ab73-4e16-9f14-44a311ff9a2f",
      "name": "Verify_OLD_Slot",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst allRows = $input.all()[0]?.json || [];\nconst state = input.current_state;\nconst oldBooking = input.current_booking;\n\n// Find old booking row (database-level matching by Booking ID or Telegram details)\nconst oldRow = allRows.find(row => {\n    const rowBookingId = row['Booking ID'] || row['booking_id'] || '';\n    const rowPhone = row['Patient Phone'] || row['patient_phone'] || '';\n    const rowStatus = row['Status'] || row['status'] || '';\n    \n    const isBooked = rowStatus.toUpperCase() === 'BOOKED';\n    const matchesBookingId = input.booking_id && rowBookingId === input.booking_id;\n    const matchesTelegram = rowPhone.includes(String(input.chat_id)) || (state.username && rowPhone.includes(state.username));\n\n    return isBooked && (matchesBookingId || matchesTelegram);\n});\n\nif (!oldRow) {\n    return [{\n        json: {\n            chat_id: input.chat_id,\n            reply_text: \"⚠️ Your original booking could not be found in our active database records. Let's make a new booking instead!\",\n            state_delta: {\n                step: \"MENU\",\n                intent: \"RESCHEDULE\",\n                action: \"ASK_USER\",\n                context: {\n                    ...state.context,\n                    booking_id: null,\n                    calendar_event_id: null,\n                    selected_doctor: null,\n                    selected_date: null,\n                    selected_slot: null\n                }\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"res_old_changed\"\n        }\n    }];\n}\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        old_booking_id: oldRow['Booking ID'] || oldRow['booking_id'] || input.booking_id,\n        old_calendar_event_id: oldRow['Calendar Event ID'] || oldRow['calendar_event_id'] || input.calendar_event_id,\n        new_slot: input.new_slot,\n        new_slot_row: input.new_slot_row,\n        current_state: state,\n        proceed_to_swap: true\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1264,
        112
      ],
      "id": "e5fbb16c-a8db-4af6-983d-89eca39f5e85",
      "name": "Validate_Swap"
    },
    {
      "parameters": {
        "operation": "delete",
        "calendar": {
          "__rl": true,
          "value": "2174f9a8fabdf573966591e3e2d8e606a068d48ee1ddbcdb2dad58fe70341800@group.calendar.google.com",
          "mode": "list",
          "cachedResultName": "Doctor Appointments"
        },
        "eventId": "={{ $('Validate_Swap').item.json.old_calendar_event_id }}",
        "options": {}
      },
      "type": "n8n-nodes-base.googleCalendar",
      "typeVersion": 1.3,
      "position": [
        1856,
        112
      ],
      "id": "033ad81f-5e49-4753-a60e-fca4a6d05a1c",
      "name": "Delete_OLD_Calendar",
      "credentials": {
        "googleCalendarOAuth2Api": {
          "id": "7qrcSH511UKOGGlN",
          "name": "Google Calendar account"
        }
      }
    },
    {
      "parameters": {
        "calendar": {
          "__rl": true,
          "value": "2174f9a8fabdf573966591e3e2d8e606a068d48ee1ddbcdb2dad58fe70341800@group.calendar.google.com",
          "mode": "list",
          "cachedResultName": "Doctor Appointments"
        },
        "start": "={{ $json.new_slot.date }}T{{ $json.new_slot.time_slot.split('-')[0] }}:00",
        "end": "={{ $json.new_slot.date }}T{{ $json.new_slot.time_slot.split('-')[1] }}:00",
        "additionalFields": {
          "description": "={{ 'Rescheduled appointment\\nPatient: ' + $json.current_state.username + '\\nChat ID: ' + $json.chat_id }}",
          "sendUpdates": "all",
          "summary": "={{ 'Rescheduled: ' + $json.current_state.username + ' with ' + $json.new_slot.doctor }}"
        }
      },
      "type": "n8n-nodes-base.googleCalendar",
      "typeVersion": 1.3,
      "position": [
        1632,
        112
      ],
      "id": "e44e3b04-17a2-467f-b086-f4535fb2ff86",
      "name": "Create_NEW_Calendar",
      "credentials": {
        "googleCalendarOAuth2Api": {
          "id": "7qrcSH511UKOGGlN",
          "name": "Google Calendar account"
        }
      }
    },
    {
      "parameters": {
        "operation": "update",
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "Status": "AVAILABLE",
            "Patient Phone": "",
            "Booking ID": "",
            "Calendar Event ID": ""
          },
          "matchingColumns": [
            "Booking ID"
          ],
          "schema": []
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        2304,
        112
      ],
      "id": "65d03471-9f6a-4500-ac24-fb77c67ed3da",
      "name": "Free_OLD_Slot",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "operation": "update",
        "documentId": {
          "__rl": true,
          "value": "={{ $env.GOOGLE_SHEETS_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "={{ $env.GOOGLE_SHEET_AVAILABILITY }}",
          "mode": "name"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "Status": "BOOKED",
            "Patient Phone": "={{ $json.patient_phone }}",
            "Calendar Event ID": "={{ $json.new_event_id }}",
            "Version": "1"
          },
          "matchingColumns": [
            "Booking ID"
          ],
          "schema": []
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        2832,
        96
      ],
      "id": "8fbfed9b-a134-4658-bdae-eaacd2995e09",
      "name": "Confirm_NEW_Slot",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state;\nconst newSlot = input.new_slot;\n\nconst name = state.username || state.first_name || 'there';\nconst patientName = state.context.patient_name || name;\n\n// Increment total reschedules\nstate.meta.total_reschedules = (state.meta.total_reschedules || 0) + 1;\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        reply_text: `✨ *All Done, ${name}!*\\n\\nI've successfully updated your appointment. Your previous booking is released, and your new timing is confirmed:\\n\\n👤 *Patient*: ${patientName}\\n👨‍⚕️ *Doctor*: ${newSlot.doctor}\\n📅 *New Date*: ${newSlot.date}\\n⏰ *New Time*: ${newSlot.time_slot}\\n\\nDr. ${newSlot.doctor} will be ready to see you then! Say *menu* to see other options or *view* to check active appointment details.`,\n        state_delta: {\n            step: \"CONFIRMED\",\n            intent: \"RESCHEDULE\",\n            action: \"EXECUTE_RESCHEDULE\",\n            context: {\n                ...state.context,\n                selected_doctor: newSlot.doctor,\n                selected_date: newSlot.date,\n                selected_slot: newSlot.time_slot,\n                booking_id: input.new_booking_id,\n                calendar_event_id: input.new_event_id,\n                original_booking_id: null,\n                original_calendar_event_id: null\n            }\n        },\n        current_state: state,\n        requires_sub_workflow: false,\n        source: \"res_confirmed\"\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        3040,
        80
      ],
      "id": "f0f12737-22c9-477b-a9a4-2e8995947a5f",
      "name": "Build_Success_Response"
    },
    {
      "parameters": {
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.7,
      "position": [
        720,
        -224
      ],
      "id": "0d31ad4b-a552-43b5-bf31-c56d99e0cfb9",
      "name": "Get row(s) in sheet",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "pxYllaqqeJxxOxpj",
          "name": "Google Sheets account 2"
        }
      }
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "check-step",
              "leftValue": "={{ $json.current_state.step }}",
              "rightValue": "AWAITING_RESCHEDULE_SLOT",
              "operator": {
                "type": "string",
                "operation": "equals"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        -352,
        80
      ],
      "id": "96d1bd7e-23e1-4364-82e6-e2750489e7e0",
      "name": "Branch_Reschedule_Flow"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "check-proceed",
              "leftValue": "={{ $json.proceed_to_fetch }}",
              "rightValue": "true",
              "operator": {
                "type": "boolean",
                "operation": "true"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        96,
        -240
      ],
      "id": "4057d4e9-4b5d-4212-9568-d481096e4f39",
      "name": "Has_Active_Booking"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state;\nconst slotOptions = state.context.slot_options || [];\nconst messageText = input.message_text || '';\n\nlet selectedIndex = parseInt(messageText.trim()) - 1;\nif (isNaN(selectedIndex) || selectedIndex < 0 || selectedIndex >= slotOptions.length) {\n    const timeMatch = slotOptions.findIndex(opt => \n        messageText.includes(opt.time_slot)\n    );\n    if (timeMatch >= 0) selectedIndex = timeMatch;\n}\n\nif (selectedIndex < 0 || selectedIndex >= slotOptions.length) {\n    return [{\n        json: {\n            chat_id: input.chat_id,\n            reply_text: `⚠️ Invalid selection. Please reply with a number from 1 to ${slotOptions.length}.\\n\\nOr say *menu* to start over.`,\n            state_delta: {\n                step: \"AWAITING_RESCHEDULE_SLOT\",\n                intent: \"RESCHEDULE\",\n                action: \"ASK_USER\",\n                context: state.context\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"res_invalid_slot\"\n        }\n    }];\n}\n\nconst selectedSlot = slotOptions[selectedIndex];\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        new_slot: selectedSlot,\n        row_number: selectedSlot.row_index, // maps directly as row_number for Lock_NEW_Slot\n        new_slot_row: selectedSlot.row_index,\n        current_state: state,\n        message_id: input.message_id,\n        proceed_to_lock: True\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -96,
        384
      ],
      "id": "9ba584a4-7cac-4b03-81b0-deeb59cc02b7",
      "name": "Validate_Reschedule_Slot"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "check-proceed-lock",
              "leftValue": "={{ $json.proceed_to_lock }}",
              "rightValue": "true",
              "operator": {
                "type": "boolean",
                "operation": "true"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [
        112,
        384
      ],
      "id": "edd66e39-ce27-4803-a918-3c544526fc33",
      "name": "New_Selection_Valid"
    },
    {
      "parameters": {
        "jsCode": "const swapOutput = $('Validate_Swap').first().json;\nconst newCalendarOutput = $('Create_NEW_Calendar').first().json;\nconst state = swapOutput.current_state;\nconst context = state.context;\n\nconst bookingType = context.booking_type || 'SELF';\nlet patientDetails = \"\";\n\nif (bookingType === 'OTHERS') {\n    const parentName = state.username || state.first_name || 'Parent';\n    patientDetails = `Name: ${context.patient_name} | Phone: ${context.patient_phone} | Telegram: @${state.username || 'user'} (Parent) | Chat: ${swapOutput.chat_id}`;\n} else {\n    const firstName = state.username || state.first_name || 'Patient';\n    const username = state.username ? ` (@${state.username})` : '';\n    patientDetails = `Name: ${firstName}${username} | Telegram Chat: ${swapOutput.chat_id}`;\n}\n\nreturn [{\n    json: {\n        chat_id: swapOutput.chat_id,\n        old_booking_id: swapOutput.old_booking_id,\n        new_booking_id: swapOutput.current_state.context.idempotency_key,\n        new_event_id: newCalendarOutput.id,\n        new_slot: swapOutput.new_slot,\n        current_state: swapOutput.current_state,\n        patient_phone: patientDetails\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        2048,
        80
      ],
      "id": "b6a49cb6-8a2a-4478-be53-94f9912594fe",
      "name": "Prepare_Reschedule_Confirm_Data"
    },
    {
      "parameters": {
        "jsCode": "const confirmOutput = $('Prepare_Reschedule_Confirm_Data').first().json;\n\nreturn [{\n    json: {\n        ...confirmOutput,\n        row_number: confirmOutput.new_row_number // Set row_number to NEW slot row for Confirm_NEW_Slot\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        2560,
        128
      ],
      "id": "bc853227-44e5-43da-891d-d3e224db038f",
      "name": "Prepare_New_Confirm_Data"
    },
    {
      "parameters": {
        "documentId": {
          "__rl": true,
          "value": "={{ $env.GOOGLE_SHEETS_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "Doctor_Schedules",
          "mode": "name"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        368,
        -256
      ],
      "id": "2aeca4a6-e933-465c-9631-3b21d49e7c9f",
      "name": "Fetch_Schedules",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "pxYllaqqeJxxOxpj",
          "name": "Google Sheets account 2"
        }
      }
    }
  ],
  "pinData": {},
  "connections": {
    "When_Executed": {
      "main": [
        [
          {
            "node": "Parse_Parent_Input",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Parse_Parent_Input": {
      "main": [
        [
          {
            "node": "Branch_Reschedule_Flow",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Lookup_Existing_Booking": {
      "main": [
        [
          {
            "node": "Has_Active_Booking",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Lock_NEW_Slot": {
      "main": [
        [
          {
            "node": "Verify_OLD_Slot",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Verify_OLD_Slot": {
      "main": [
        [
          {
            "node": "Validate_Swap",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Validate_Swap": {
      "main": [
        [
          {
            "node": "Create_NEW_Calendar",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Delete_OLD_Calendar": {
      "main": [
        [
          {
            "node": "Prepare_Reschedule_Confirm_Data",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Create_NEW_Calendar": {
      "main": [
        [
          {
            "node": "Delete_OLD_Calendar",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Free_OLD_Slot": {
      "main": [
        [
          {
            "node": "Prepare_New_Confirm_Data",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Confirm_NEW_Slot": {
      "main": [
        [
          {
            "node": "Build_Success_Response",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Get row(s) in sheet": {
      "main": [
        [
          {
            "node": "Filter_Format_New_Slots",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Branch_Reschedule_Flow": {
      "main": [
        [
          {
            "node": "Validate_Reschedule_Slot",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Lookup_Existing_Booking",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Has_Active_Booking": {
      "main": [
        [
          {
            "node": "Fetch_Schedules",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Validate_Reschedule_Slot": {
      "main": [
        [
          {
            "node": "New_Selection_Valid",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "New_Selection_Valid": {
      "main": [
        [
          {
            "node": "Lock_NEW_Slot",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Prepare_Reschedule_Confirm_Data": {
      "main": [
        [
          {
            "node": "Free_OLD_Slot",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Prepare_New_Confirm_Data": {
      "main": [
        [
          {
            "node": "Confirm_NEW_Slot",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Fetch_Schedules": {
      "main": [
        [
          {
            "node": "Get row(s) in sheet",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "active": false,
  "settings": {
    "executionOrder": "v1",
    "binaryMode": "separate"
  },
  "versionId": "3f66ffd4-8742-4ba7-b16b-f0de8029dd16",
  "meta": {
    "instanceId": "c5674022872009769c8b83e3189e707e15b254c1b9e48d6b8e871f168c7daed1"
  },
  "id": "qJANg3mblINkez82",
  "tags": []
}
``


### CANCEL_SPOKE.json

``json
{
  "name": "CANCEL_SPOKE",
  "nodes": [
    {
      "parameters": {
        "inputSource": "passthrough"
      },
      "type": "n8n-nodes-base.executeWorkflowTrigger",
      "typeVersion": 1.1,
      "position": [
        0,
        0
      ],
      "id": "29a89cd5-ace2-4d78-aae1-41d2b531deeb",
      "name": "When_Executed"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst parentData = input.workflowData ? JSON.parse(input.workflowData) : input;\n\nreturn [{\n    json: {\n        chat_id: parentData.chat_id,\n        user_id: parentData.user_id,\n        username: parentData.username,\n        message_text: parentData.message_text,\n        message_id: parentData.message_id,\n        current_state: parentData.current_state,\n        entities: parentData.entities || {},\n        llm_output: parentData.llm_output || {},\n        action: parentData.action,\n        intent: parentData.intent,\n        reply_text: parentData.reply_text,\n        new_step_state: parentData.new_step_state,\n        system_time: parentData.system_time\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        208,
        0
      ],
      "id": "3dfb03eb-11ff-433d-ba02-0ba24c1ec4f7",
      "name": "Parse_Parent_Input"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state;\nconst entities = input.entities;\nconst chatId = input.chat_id;\n\n// Check if we have an existing booking\nif (!state.context.booking_id) {\n    return [{\n        json: {\n            chat_id: chatId,\n            reply_text: \"❌ No active booking found to cancel.\n\nWould you like to *book* a new appointment?\",\n            state_delta: {\n                step: \"MENU\",\n                intent: \"CANCEL\",\n                action: \"ASK_USER\"\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"cancel_no_booking\"\n        }\n    }];\n}\n\n// Check for explicit confirmation\nconst confirmation = entities.confirmation === true || \n                     (input.message_text || '').toLowerCase().match(/^(yes|confirm|delete|proceed|cancel it|do it)$/);\n\nif (!confirmation) {\n    // Ask for explicit confirmation\n    return [{\n        json: {\n            chat_id: chatId,\n            reply_text: `⚠️ *Cancel Booking Confirmation*\n\nYou have an appointment with:\n👨‍⚕️ ${state.context.selected_doctor}\n📅 ${state.context.selected_date}\n⏰ ${state.context.selected_slot}\n\nType *YES* to confirm cancellation, or say *menu* to keep your booking.`,\n            state_delta: {\n                step: \"CONFIRM_CANCEL\",\n                intent: \"CANCEL\",\n                action: \"ASK_USER\",\n                context: state.context\n            },\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"cancel_ask_confirm\"\n        }\n    }];\n}\n\n// Confirmed - proceed to cancel\nreturn [{\n    json: {\n        chat_id: chatId,\n        booking_id: state.context.booking_id,\n        calendar_event_id: state.context.calendar_event_id,\n        current_booking: {\n            doctor: state.context.selected_doctor,\n            date: state.context.selected_date,\n            slot: state.context.selected_slot\n        },\n        current_state: state,\n        message_id: input.message_id,\n        proceed_to_cancel: true\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        400,
        0
      ],
      "id": "cddc2963-d21f-4080-943f-c04ad6f27559",
      "name": "Check_Confirmation_Gate"
    },
    {
      "parameters": {
        "operation": "delete",
        "calendar": {
          "__rl": true,
          "value": "2174f9a8fabdf573966591e3e2d8e606a068d48ee1ddbcdb2dad58fe70341800@group.calendar.google.com",
          "mode": "list",
          "cachedResultName": "Doctor Appointments"
        },
        "eventId": "={{ $json.calendar_event_id }}",
        "options": {}
      },
      "type": "n8n-nodes-base.googleCalendar",
      "typeVersion": 1.3,
      "position": [
        608,
        0
      ],
      "id": "9cbbb9fb-4732-4efd-961f-43ae761c6d2c",
      "name": "Delete_Calendar_Event",
      "credentials": {
        "googleCalendarOAuth2Api": {
          "id": "7qrcSH511UKOGGlN",
          "name": "Google Calendar account"
        }
      }
    },
    {
      "parameters": {
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        800,
        0
      ],
      "id": "14e976f4-bb49-4fbc-824f-ff022e7c88e5",
      "name": "Find_Sheet_Row",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst allRows = $input.all()[0]?.json || [];\nconst booking = input.current_booking;\nconst chatId = input.chat_id;\n\n// Find the booking row\nconst targetRow = allRows.find(row => {\n    const rowDoctor = row['Doctor'] || row['doctor'] || '';\n    const rowDate = row['Date'] || row['date'] || '';\n    const rowTime = row['Time Slot'] || row['time_slot'] || '';\n    return rowDoctor.toLowerCase() === booking.doctor.toLowerCase() && \n           rowDate === booking.date && \n           rowTime === booking.slot;\n});\n\nif (!targetRow) {\n    return [{\n        json: {\n            chat_id: chatId,\n            row_found: false,\n            row_number: null\n        }\n    }];\n}\n\nreturn [{\n    json: {\n        chat_id: chatId,\n        row_found: true,\n        row_number: targetRow['__row_number'] || targetRow.rowIndex,\n        row_data: targetRow\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1008,
        0
      ],
      "id": "3b002ea5-096f-42d1-9d38-58052b7c5fc0",
      "name": "Identify_Row"
    },
    {
      "parameters": {
        "operation": "update",
        "documentId": {
          "__rl": true,
          "value": "1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww",
          "mode": "list",
          "cachedResultName": "Doctor Appointment System",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit?usp=drivesdk"
        },
        "sheetName": {
          "__rl": true,
          "value": "gid=0",
          "mode": "list",
          "cachedResultName": "Availability",
          "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1AFWYcUJ7sgiDn73Yq4l4ZwFVdskHVa4ZJhiQVmTYkww/edit#gid=0"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {},
          "matchingColumns": [
            "Booking ID"
          ],
          "schema": [
            {
              "id": "Date",
              "displayName": "Date",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": true
            },
            {
              "id": "Doctor",
              "displayName": "Doctor",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": true
            },
            {
              "id": "Time Slot",
              "displayName": "Time Slot",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": true
            },
            {
              "id": "Status",
              "displayName": "Status",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": true
            },
            {
              "id": "Patient Phone",
              "displayName": "Patient Phone",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": true
            },
            {
              "id": "Booking ID",
              "displayName": "Booking ID",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": false
            },
            {
              "id": "Calendar Event ID",
              "displayName": "Calendar Event ID",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": true
            },
            {
              "id": "Version",
              "displayName": "Version",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "string",
              "canBeUsedToMatch": true,
              "removed": true
            },
            {
              "id": "row_number",
              "displayName": "row_number",
              "required": false,
              "defaultMatch": false,
              "display": true,
              "type": "number",
              "canBeUsedToMatch": true,
              "readOnly": true,
              "removed": true
            }
          ],
          "attemptToConvertTypes": false,
          "convertFieldsToString": false
        },
        "options": {}
      },
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [
        1200,
        0
      ],
      "id": "da47c4fd-9302-4291-80ee-ba48bf7c474d",
      "name": "Clear_Sheet_Row",
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "XagyomCRXbVdMno2",
          "name": "Google Sheets account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state;\nconst booking = input.current_booking;\n\nreturn [{\n    json: {\n        chat_id: input.chat_id,\n        reply_text: `✅ *Booking Cancelled*\n\nYour appointment with ${booking.doctor} on ${booking.date} at ${booking.slot} has been cancelled.\n\nThe slot is now available for other patients.\n\nSay *book* to make a new appointment or *menu* to see options.`,\n        state_delta: {\n            step: \"MENU\",\n            intent: \"CANCEL\",\n            action: \"EXECUTE_CANCEL\",\n            context: {\n                ...state.context,\n                selected_doctor: null,\n                selected_date: null,\n                selected_slot: null,\n                booking_id: null,\n                calendar_event_id: null,\n                original_booking_id: null,\n                original_calendar_event_id: null,\n                slot_options: [],\n                last_question: null,\n                retry_count: 0\n            }\n        },\n        current_state: state,\n        requires_sub_workflow: false,\n        source: \"cancel_confirmed\"\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        1408,
        0
      ],
      "id": "cdd66b2c-a4fe-4fac-86e4-77c2b5669097",
      "name": "Build_Success_Response"
    }
  ],
  "pinData": {},
  "connections": {
    "When_Executed": {
      "main": [
        [
          {
            "node": "Parse_Parent_Input",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Parse_Parent_Input": {
      "main": [
        [
          {
            "node": "Check_Confirmation_Gate",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Check_Confirmation_Gate": {
      "main": [
        [
          {
            "node": "Delete_Calendar_Event",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Delete_Calendar_Event": {
      "main": [
        [
          {
            "node": "Find_Sheet_Row",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Find_Sheet_Row": {
      "main": [
        [
          {
            "node": "Identify_Row",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Identify_Row": {
      "main": [
        [
          {
            "node": "Clear_Sheet_Row",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Clear_Sheet_Row": {
      "main": [
        [
          {
            "node": "Build_Success_Response",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "active": false,
  "settings": {
    "executionOrder": "v1",
    "binaryMode": "separate"
  },
  "versionId": "006e0c22-2383-429a-bdea-7361ad4b77c5",
  "meta": {
    "templateCredsSetupCompleted": true,
    "instanceId": "c5674022872009769c8b83e3189e707e15b254c1b9e48d6b8e871f168c7daed1"
  },
  "id": "hErtBXBzdwcPADKK",
  "tags": []
}
``


### FAQ_SPOKE.json

``json
{
  "name": "FAQ_SPOKE",
  "nodes": [
    {
      "parameters": {
        "inputSource": "passthrough"
      },
      "type": "n8n-nodes-base.executeWorkflowTrigger",
      "typeVersion": 1.1,
      "position": [
        -2832,
        -736
      ],
      "id": "6b606d96-89a6-42d2-bce1-3a40bed26638",
      "name": "When_Executed"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst parentData = input.workflowData ? JSON.parse(input.workflowData) : input;\n\nreturn [{\n    json: {\n        chat_id: parentData.chat_id,\n        user_id: parentData.user_id,\n        username: parentData.username,\n        message_text: parentData.message_text,\n        message_id: parentData.message_id,\n        current_state: parentData.current_state,\n        entities: parentData.entities || {},\n        llm_output: parentData.llm_output || {},\n        action: parentData.action,\n        intent: parentData.intent,\n        reply_text: parentData.reply_text,\n        new_step_state: parentData.new_step_state,\n        system_time: parentData.system_time\n    }\n}];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -2640,
        -736
      ],
      "id": "8645f328-54f9-4968-93fa-b7692e5a2626",
      "name": "Parse_Parent_Input"
    },
    {
      "parameters": {
        "jsCode": "const input = $input.first().json;\nconst state = input.current_state || {};\nconst messageText = (input.message_text || \"\").toLowerCase();\n\n// Static FAQ knowledge base\nconst faqDB = {\n    hours: `🏥 *Clinic Hours*\n\nMonday - Friday: 8:00 AM - 6:00 PM\nSaturday: 9:00 AM - 2:00 PM\nSunday: Closed\n\nEmergency services available 24/7.`,\n\n    location: `📍 *Location*\n\n123 Medical Center Drive\nDowntown Health District\n\nLandmark: Next to City Hospital\nParking: Free underground parking available`,\n\n    contact: `📞 *Contact*\n\nPhone: +1 (555) 123-4567\nEmail: appointments@clinic.com\nWhatsApp: Same as phone number\n\nFor emergencies, call our 24/7 hotline.`,\n\n    insurance: `💳 *Insurance*\n\nWe accept:\n• Blue Cross Blue Shield\n• Aetna\n• UnitedHealthcare\n• Medicare\n• Most major PPO plans\n\nPlease bring your insurance card to your appointment.`,\n\n    doctors: `👨‍⚕️ *Our Doctors*\n\n• Dr. Smith - Cardiology (Mon-Fri)\n• Dr. Jones - Dermatology (Mon, Wed, Fri)\n• Dr. Lee - General Medicine (Mon-Sat)\n\nAll doctors are board-certified with 10+ years experience.`,\n\n    fees: `💰 *Consultation Fees*\n\n• General Consultation: $80\n• Specialist Consultation: $120\n• Follow-up: $50\n\nInsurance co-pays vary by plan. Cash/card accepted.`,\n\n    cancel: `❌ *Cancellation Policy*\n\n• Free cancellation up to 24 hours before\n• Same-day cancellation: $25 fee\n• No-show: $50 fee\n\nUse this bot to cancel anytime.`,\n\n    prepare: `📝 *Before Your Visit*\n\n• Bring ID and insurance card\n• Arrive 15 minutes early\n• List current medications\n• Fasting required for blood tests (8 hours)\n• Previous medical records if any`,\n\n    covid: `😷 *COVID Protocol*\n\n• Masks optional but recommended\n• Hand sanitizer available at entrance\n• Separate waiting area for respiratory symptoms\n• Telemedicine available for minor issues`,\n\n    emergency: `🚨 *Emergency?*\n\nIf this is a life-threatening emergency, call 911 immediately.\n\nFor urgent non-emergency care:\n• Visit our Urgent Care (walk-in)\n• Call our 24/7 nurse line: +1 (555) 999-8888`\n};\n\n// Match keywords\nlet matchedKey = null;\n\nconst keywords = {\n    hours: [\"hour\", \"open\", \"close\", \"time\", \"when\", \"schedule\", \"available\"],\n    location: [\"location\", \"address\", \"where\", \"find\", \"direction\", \"map\", \"place\"],\n    contact: [\"contact\", \"phone\", \"email\", \"call\", \"reach\", \"number\"],\n    insurance: [\"insurance\", \"cover\", \"payment\", \"accept\", \"plan\", \"policy\"],\n    doctors: [\"doctor\", \"specialist\", \"physician\", \"who\", \"dr.\"],\n    fees: [\"fee\", \"cost\", \"price\", \"charge\", \"payment\", \"how much\", \"expensive\"],\n    cancel: [\"cancel policy\", \"cancellation\", \"no show\", \"miss\", \"late\"],\n    prepare: [\"prepare\", \"bring\", \"need\", \"before\", \"visit\", \"what to\"],\n    covid: [\"covid\", \"mask\", \"vaccine\", \"protocol\", \"safety\"],\n    emergency: [\"emergency\", \"urgent\", \"911\", \"critical\", \"severe\", \"pain\"]\n};\n\n// Find matching FAQ category\nfor (const [key, words] of Object.entries(keywords)) {\n    if (words.some(word => messageText.includes(word))) {\n        matchedKey = key;\n        break;\n    }\n}\n\n// Generate reply\nlet reply;\n\nif (matchedKey && faqDB[matchedKey]) {\n    reply = faqDB[matchedKey];\n} else {\n    reply = `🤔 I don't have a specific answer for that.\n\nHere are topics I can help with:\n• Hours & Location\n• Doctors & Specialties\n• Fees & Insurance\n• Preparation & Policies\n• Contact & Emergency\n\nOr say *menu* to book an appointment.`;\n}\n\n// Return response\nreturn [\n    {\n        json: {\n            chat_id: input.chat_id,\n            reply_text: reply,\n            state_delta: {},\n            current_state: state,\n            requires_sub_workflow: false,\n            source: \"faq_answered\"\n        }\n    }\n];"
      },
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [
        -2432,
        -736
      ],
      "id": "22398956-888b-42ce-a8e5-b7e4672a21b8",
      "name": "FAQ_Knowledge_Base"
    }
  ],
  "pinData": {},
  "connections": {
    "When_Executed": {
      "main": [
        [
          {
            "node": "Parse_Parent_Input",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Parse_Parent_Input": {
      "main": [
        [
          {
            "node": "FAQ_Knowledge_Base",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "active": false,
  "settings": {
    "executionOrder": "v1",
    "binaryMode": "separate"
  },
  "versionId": "66912734-3522-4ef5-a1d3-85f9adf492c7",
  "meta": {
    "templateCredsSetupCompleted": true,
    "instanceId": "c5674022872009769c8b83e3189e707e15b254c1b9e48d6b8e871f168c7daed1"
  },
  "id": "blPNEkC6RtYPVFkB",
  "tags": []
}
``

