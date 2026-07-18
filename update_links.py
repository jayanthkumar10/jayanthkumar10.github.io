import os
import re

portfolio_dir = "c:/Git_Portfolio"

def update_file(filename, replacements):
    path = os.path.join(portfolio_dir, filename)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# 1. Update index.html
with open(os.path.join(portfolio_dir, 'index.html'), 'r', encoding='utf-8') as f:
    index_html = f.read()

# Extract WhatsApp Block
whatsapp_start = index_html.find('<!-- PROJECT 2 -->')
project_3_start = index_html.find('<!-- PROJECT 3 -->')
whatsapp_block = index_html[whatsapp_start:project_3_start]

# Remove WhatsApp Block from original position
index_html = index_html[:whatsapp_start] + index_html[project_3_start:]

# Find the end of Project 4 (PulseOps) to insert WhatsApp Block at the end
pulseops_end = index_html.find('      </div>\n    </div>\n  </section>\n\n  <!-- EXPERIENCE -->')
index_html = index_html[:pulseops_end] + whatsapp_block + index_html[pulseops_end:]

# Fix the Project comments to match new order
index_html = index_html.replace('<!-- PROJECT 3 -->', '<!-- PROJECT 2 -->', 1)
index_html = index_html.replace('<!-- PROJECT 4 -->', '<!-- PROJECT 3 -->', 1)
last_proj2 = index_html.rfind('<!-- PROJECT 2 -->')
index_html = index_html[:last_proj2] + '<!-- PROJECT 4 -->' + index_html[last_proj2+18:]

# Replace Links in index.html
# Pathlight GitHub
index_html = re.sub(r'<a href="#"([^>]*?)>\s*\[↗ GitHub Repo\]\s*</a>', r'<a href="https://github.com/jayanthkumar10/PathLight.ai" target="_blank"\1>\n                    [↗ GitHub Repo]\n                  </a>', index_html, count=1)
# Pathlight Live Demo - Remove
index_html = re.sub(r'<a href="project-ai-job-companion.html"([^>]*?)>\s*\[↗ Live Demo\]\s*</a>', '', index_html, count=1)

# PulseOps GitHub
index_html = re.sub(r'<a href="#"([^>]*?)>\s*\[↗ GitHub Repo\]\s*</a>', r'<a href="https://github.com/jayanthkumar10/PulseOps-.git" target="_blank"\1>\n                    [↗ GitHub Repo]\n                  </a>', index_html, count=1)

with open(os.path.join(portfolio_dir, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(index_html)

# 2. Update Pathlight Case Study
update_file('project-ai-job-companion.html', [
    ('<a href="#" class="text-sky-400 hover:text-sky-300 font-mono text-xs flex items-center gap-2 transition-colors">\n          [↗ GitHub]\n        </a>', 
     '<a href="https://github.com/jayanthkumar10/PathLight.ai" target="_blank" class="text-sky-400 hover:text-sky-300 font-mono text-xs flex items-center gap-2 transition-colors">\n          [↗ GitHub]\n        </a>'),
    ('<a href="#" class="text-sky-400 hover:text-sky-300 font-mono text-xs flex items-center gap-2 transition-colors">\n          [↗ Live Demo]\n        </a>',
     ''),
    ('<a href="project-pulseops-ai.html" class="text-zinc-100 hover:text-sky-400 font-medium transition-colors">PulseOps AI →</a>',
     '<a href="project-heart-disease.html" class="text-zinc-100 hover:text-sky-400 font-medium transition-colors">Heart Disease Prediction →</a>')
])

# 3. Update Heart Disease Case Study
update_file('project-heart-disease.html', [
    ('<a href="#" class="text-sky-400 hover:text-sky-300 font-mono text-xs flex items-center gap-2 transition-colors">\n          [↗ GitHub]\n        </a>',
     '<a href="https://github.com/jayanthkumar10/Heart-disease-Prediction-using-Supervised-Machine-Learning-algorithms" target="_blank" class="text-sky-400 hover:text-sky-300 font-mono text-xs flex items-center gap-2 transition-colors">\n          [↗ GitHub]\n        </a>'),
    ('<a href="project-ai-job-companion.html" class="text-zinc-100 hover:text-sky-400 font-medium transition-colors">Pathlight.ai →</a>',
     '<a href="project-pulseops-ai.html" class="text-zinc-100 hover:text-sky-400 font-medium transition-colors">PulseOps AI →</a>')
])

# 4. Update PulseOps Case Study
update_file('project-pulseops-ai.html', [
    ('<a href="#" class="text-sky-400 hover:text-sky-300 font-mono text-xs flex items-center gap-2 transition-colors">\n          [↗ GitHub]\n        </a>',
     '<a href="https://github.com/jayanthkumar10/PulseOps-.git" target="_blank" class="text-sky-400 hover:text-sky-300 font-mono text-xs flex items-center gap-2 transition-colors">\n          [↗ GitHub]\n        </a>')
])

# 5. Update WhatsApp Bot Case Study
update_file('project-whatsapp-bot.html', [
    ('<a href="project-heart-disease.html" class="text-zinc-100 hover:text-sky-400 font-medium transition-colors">Heart Disease Prediction →</a>',
     '<a href="project-ai-job-companion.html" class="text-zinc-100 hover:text-sky-400 font-medium transition-colors">Pathlight.ai →</a>')
])

print("Links updated and projects reordered successfully.")
