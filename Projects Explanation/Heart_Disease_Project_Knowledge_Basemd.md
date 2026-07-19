# Heart Disease Prediction using Supervised Machine Learning

## Project Overview

This project is a machine learning application that predicts whether a
person is likely to have heart disease based on their medical
information. The primary goal was to compare multiple supervised machine
learning algorithms and determine which one performs best for this
prediction problem.

Unlike a production healthcare system, this project is educational in
nature. It demonstrates the complete machine learning workflow, starting
from loading the dataset and ending with evaluating multiple models.

------------------------------------------------------------------------

# Problem Statement

Heart disease is one of the leading causes of death worldwide. Early
prediction can help doctors identify high-risk patients and begin
preventive treatment earlier.

The objective of this project is to build a classification model that
predicts whether a patient has heart disease by learning patterns from
historical patient data.

The prediction has only two possible outcomes:

-   Presence of Heart Disease
-   Absence of Heart Disease

Because the output belongs to one of two categories, this is a **binary
classification** problem.

------------------------------------------------------------------------

# Overall Project Flow

The project follows a standard machine learning pipeline:

1.  Load the dataset.
2.  Understand the dataset using exploratory analysis.
3.  Check for missing values.
4.  Clean the data.
5.  Convert the target column into numerical values.
6.  Study relationships between features.
7.  Split the dataset into training and testing sets.
8.  Train multiple machine learning models.
9.  Evaluate each model using performance metrics.
10. Compare the models and identify the best-performing algorithm.

------------------------------------------------------------------------

# Dataset Understanding

The dataset contains medical information collected from patients.

Each row represents one patient.

Each column represents a medical attribute such as:

-   Age
-   Blood Pressure
-   Cholesterol
-   Blood Sugar
-   Chest Pain
-   Maximum Heart Rate
-   ECG Results
-   Exercise Induced Angina
-   Other clinical measurements

The final column is the target variable, indicating whether heart
disease is present or absent.

------------------------------------------------------------------------

# Data Exploration

Before training any model, the dataset is explored to understand its
structure.

The project checks:

-   Number of rows and columns
-   Sample records
-   Statistical summary
-   Data types
-   Missing values
-   Minimum and maximum values
-   Mean, median and mode

This helps verify that the dataset is suitable for machine learning.

------------------------------------------------------------------------

# Data Cleaning

Machine learning models cannot handle missing values properly.

The project checks whether any values are missing.

If missing values are found, they are replaced using **Forward Fill**,
meaning the missing value is replaced with the previous available value
from the same column.

After cleaning, the dataset is saved and reloaded to ensure consistency.

------------------------------------------------------------------------

# Feature Preparation

Machine learning algorithms work with numbers.

The target column originally contains text values:

-   Presence
-   Absence

These are converted into:

-   Presence → 1
-   Absence → 0

This allows the algorithms to understand the target variable.

------------------------------------------------------------------------

# Correlation Analysis

The project studies how strongly each feature is related to heart
disease.

Highly related features are generally more useful for prediction.

Very weakly related features contribute less information.

This step provides a better understanding of the importance of different
medical attributes.

------------------------------------------------------------------------

# Train-Test Split

The dataset is divided into two parts:

## Training Data

Used by the model to learn patterns.

## Testing Data

Used only after training to evaluate how well the model performs on
unseen data.

The project uses:

-   80% Training Data
-   20% Testing Data

This prevents evaluating the model on data it has already seen.

------------------------------------------------------------------------

# Machine Learning Models Used

Instead of depending on a single algorithm, the project compares several
popular supervised learning models.

## Logistic Regression

Used as the baseline classification algorithm.

It predicts the probability that a patient belongs to either the heart
disease or no-heart-disease category.

------------------------------------------------------------------------

## Support Vector Machine (SVM)

Creates the best possible boundary between the two classes to improve
classification accuracy.

------------------------------------------------------------------------

## K-Nearest Neighbors (KNN)

Predicts the result by looking at patients with similar medical
characteristics.

------------------------------------------------------------------------

## Naive Bayes

Uses probability to estimate which class is more likely.

It is simple, fast and performs well on many classification tasks.

------------------------------------------------------------------------

## Decision Tree

Makes predictions by repeatedly asking simple decision questions based
on patient attributes.

The final prediction is reached through a tree-like structure.

------------------------------------------------------------------------

## Random Forest

Combines many decision trees.

Each tree votes for a prediction.

The majority vote becomes the final prediction.

Random Forest usually provides better stability than a single Decision
Tree.

------------------------------------------------------------------------

# Model Evaluation

After training, every model makes predictions on the testing dataset.

The project evaluates each model using:

## Accuracy

Percentage of correct predictions.

## Precision

Measures how many predicted positive cases are actually positive.

## Recall

Measures how many actual positive cases were successfully identified.

## F1 Score

Balances Precision and Recall into one metric.

## Specificity

Measures how well the model identifies patients without heart disease.

## Confusion Matrix

Shows:

-   Correct Positive Predictions
-   Correct Negative Predictions
-   False Positives
-   False Negatives

This provides a complete picture of model performance.

------------------------------------------------------------------------

# Cross Validation

A single train-test split may sometimes give optimistic or pessimistic
results.

To obtain a more reliable estimate, the project performs 5-fold Cross
Validation.

The dataset is divided into five parts.

Each part becomes the testing dataset once while the remaining parts are
used for training.

The final accuracy is calculated as the average across all five runs.

This provides a more dependable estimate of model performance.

------------------------------------------------------------------------

# Model Comparison

The project compares all trained algorithms using their accuracy scores.

This helps identify which algorithm performs best on this dataset
instead of assuming that one particular algorithm is always superior.

------------------------------------------------------------------------

# Key Learning Outcomes

Through this project, I learned:

-   How a complete machine learning workflow is structured.
-   The importance of understanding data before training a model.
-   Why data cleaning directly impacts prediction quality.
-   Why the dataset should be split into training and testing sets.
-   How different supervised learning algorithms solve the same
    classification problem differently.
-   Why evaluation metrics such as Precision, Recall and F1 Score are
    important instead of relying only on Accuracy.
-   How Cross Validation provides a more reliable estimate of model
    performance.
-   How to compare multiple algorithms objectively before selecting the
    best model.

------------------------------------------------------------------------

# Interview Explanation (2--3 Minutes)

"This project focuses on predicting whether a patient is likely to have
heart disease using supervised machine learning. I started by
understanding and cleaning the dataset, ensuring there were no missing
values and converting the target labels into numerical form. After
exploring the data and studying the relationships between different
medical features, I divided the dataset into training and testing sets.

Instead of relying on a single algorithm, I trained multiple supervised
learning models including Logistic Regression, Support Vector Machine,
K-Nearest Neighbors, Naive Bayes, Decision Tree and Random Forest. I
evaluated each model using Accuracy, Precision, Recall, F1 Score and
Confusion Matrix to understand their strengths and weaknesses. Finally,
I performed 5-fold Cross Validation to obtain a more reliable estimate
of model performance.

The biggest takeaway from this project was understanding the complete
end-to-end machine learning pipeline---from data preparation to model
comparison and evaluation---rather than focusing on only one algorithm."

------------------------------------------------------------------------

# Conclusion

This project demonstrates a complete supervised machine learning
workflow for a healthcare prediction problem. It emphasizes proper data
preparation, comparison of multiple algorithms, and objective evaluation
using standard performance metrics. The overall goal is not only to
achieve good prediction accuracy but also to understand the entire
process of building and evaluating machine learning models.

Code for the project below 
do not answer with explaining the code untill unless the interviewer asks about the code 
# Heart Disease Prediction Using Supervised Machine Learning Algorithms


```python
#installing dependecies 
!pip install numpy pandas matplotlib seaborn
```


```python
#importing the libraries
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
```


```python
#reading the data set
dataset = pd.read_csv("Heart_Disease_Prediction.csv")
```

**Data Preprocessing/Data Cleaning**


```python
dataset.shape #returns the dimensions of the array
```


```python
dataset.head(5) #returns the first 5 rows of the dataset method is commonly used
#to quickly inspect the structure and content of a data frame, especially when working with large data sets.    
```


```python
dataset.describe() #he method calculates several common statistics, such as the
# count, mean, standard deviation, minimum, maximum, and quartiles for each numeric column in the data frame
```

**Checking for NULL values**


```python
dataset.isnull()
```


```python
dataset.isnull().sum()
```

**Replacing the missing values with Last observed carry forward**



```python
dataset.fillna(method='ffill',inplace=True)

#save the cleaned dataset

dataset.to_csv('cleaned_heartdisease_dataset.csv',index= False)
```

fillna()     ->    Function to fill missing (NaN) values<br>
method='ffill   ->   'Forward fill → LOCF <br>
inplace=True   ->   Modifies the DataFrame directly (no new copy)


```python
#reading the new dataset without null values
df=pd.read_csv('cleaned_heartdisease_dataset.csv')
```


```python
df.isnull()
```


```python
#checking if still nall values existed 
df.isnull().sum()
```


```python
for col in df.columns:
    print(col, len(df[col].unique()))
```


```python
means = df.mean(numeric_only=True)
print(means)
```


```python
modes = df.mode()

# Iterate over each column and print the mode
for column in modes.columns:
    print(f"Mode of {column}: {modes[column][0]}")
```


```python
medians = df.median(numeric_only = True)
print(medians)
```


```python
maxi = df.max()
print(maxi)
```


```python
mini = df.min()
print(mini)
```


```python
df.info()
```


```python
df["Heart Disease"] = df["Heart Disease"].map({
    "Absence": 0,
    "Presence": 1
})
```


```python
corr = df.corr()["Heart Disease"].abs().sort_values(ascending=False)
print(corr)
```

**From the above information it shows that most columns are moderately correlated with target, but 'fbs' is very weakly correlated.**


```python
df.corr()
```

**Splitting the df to Train and Test**


```python
from sklearn.model_selection import train_test_split
```


```python
X = df.drop(["Heart Disease"],axis=1) # “X represents feature variables used by the model for learning patterns.
Y = df["Heart Disease"] #Y is the target/output/label.

x_train,x_test,y_train,y_test = train_test_split(X,Y,test_size=0.20,random_state=64)
```


```python
x_train.shape #training input data
```


```python
x_test.shape #this is unseen data model doesnt see this data while training 
```


```python
y_train.shape #this has the correct answer for x_train
```


```python
y_test.shape # actual answers for the test data 
```

**Logistic Regression**

Logisitic regression is used for classification problems . <br>
**Logistic Regression is a supervised classification algorithm that predicts the probability of a categorical outcome using the sigmoid function** <br>
Linear regression predicts the exact number<br>
example : salary prediction, temperatiure prediction <br>
whereas logistic regression predicts the probablity of category<br>
example : disease yes/no<br>


```python
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score

lr = LogisticRegression()
lr.fit(x_train,y_train)
Y_pred_lr = lr.predict(x_test)
```


```python
score_lr = round(accuracy_score(Y_pred_lr,y_test)*100,2)
print("The accuracy score achieved using Logistic Regression is: "+str(score_lr)+" %")
```

**Confusion Matrix**


```python
import seaborn as sns
import matplotlib.pyplot as plt
```


```python
from sklearn.metrics import confusion_matrix
matrix= confusion_matrix(y_test, Y_pred_lr)
```


```python
import seaborn as sns
import matplotlib.pyplot as plt

# Plot heatmap
sns.heatmap(matrix, annot=True, fmt="d")

# Save figure
plt.savefig("logistic_regr_confuse.png")

# Display plot
plt.show()

```


```python
from sklearn.metrics import confusion_matrix
confusion = confusion_matrix(y_test, Y_pred_lr)
print('Confusion Matrix\n')
print(confusion)
```


```python
from sklearn.metrics import precision_score
precision = precision_score(y_test, Y_pred_lr)
print("Precision for logistic regression: ",precision)
```


```python
from sklearn.metrics import recall_score
recall = recall_score(y_test, Y_pred_lr)
print("Recall for logistic regression:", recall)
```


```python
print("F1 Score for logistic regression :",(2*precision*recall)/(precision+recall))
```


```python
rate_lr = accuracy_score(Y_pred_lr,y_test)
rate = 1-rate_lr
print("Miss classification Rate : ",rate)
```


```python
ConfusionMatrix =pd.crosstab(y_test, Y_pred_lr)
print(ConfusionMatrix)
```


```python
tn=ConfusionMatrix.iloc[0,0]
fp=ConfusionMatrix.iloc[0,1]
fn=ConfusionMatrix.iloc[1,0]
tp=ConfusionMatrix.iloc[1,1]
```


```python
specificity_lr = tn/(tn+fp)
print('specificity of logistic regression :',specificity_lr)
```

**Support Vector Machine**


```python
from sklearn import svm
from sklearn.svm import SVC

sv = svm.SVC(kernel='linear', C=0.1, gamma=0.1)

sv.fit(x_train, y_train)

Y_pred_svm = sv.predict(x_test)
```


```python
score_svm = round(accuracy_score(Y_pred_svm,y_test)*100,2)

print("The accuracy score achieved using Linear SVM is: "+str(score_svm)+" %")
```

**Confusion Matrix for Support Vector Machine**


```python
matrix_svm= confusion_matrix(y_test, Y_pred_svm)
```


```python
import seaborn as sns
import matplotlib.pyplot as plt

# Plot heatmap
sns.heatmap(matrix_svm, annot=True, fmt="d")

# Save figure
plt.savefig("svm_confuse.png")

# Display plot
plt.show()
```

**KNN**


```python
from sklearn.neighbors import KNeighborsClassifier

knn = KNeighborsClassifier(n_neighbors=5)
knn.fit(x_train,y_train)
Y_pred_knn=knn.predict(x_test)
```


```python
score_knn = round(accuracy_score(Y_pred_knn,y_test)*100,2)

print("The accuracy score achieved using KNN is: "+str(score_knn)+" %")
```

**Naive Bayes**


```python
from sklearn.naive_bayes import GaussianNB

nb = GaussianNB()

nb.fit(x_train,y_train)

Y_pred_nb = nb.predict(x_test)
```


```python
score_nb = round(accuracy_score(Y_pred_nb,y_test)*100,2)

print("The accuracy score achieved using Naive Bayes is: "+str(score_nb)+" %")
```

**Decision Tree**


```python
from sklearn.tree import DecisionTreeClassifier
dt = DecisionTreeClassifier(max_depth=4, random_state=42)

dt.fit(x_train, y_train)

y_pred_dt = dt.predict(x_test)
```


```python
score_dt = round(accuracy_score(y_pred_dt,y_test)*100,2)

print("The accuracy score achieved using Decision Tree is: "+str(score_dt)+" %")
```

**Random Forest**


```python
x_train,x_test,y_train,y_test = train_test_split(X,Y,test_size=0.20,random_state=0)
```


```python
from sklearn.ensemble import RandomForestClassifier
randfor = RandomForestClassifier(max_depth=2,n_estimators=100, random_state=0)

randfor.fit(x_train, y_train)

y_pred_rf = randfor.predict(x_test)

```


```python
score_rf = round(accuracy_score(y_pred_rf,y_test)*100,2)

print("The accuracy score achieved using Random Forest is: "+str(score_rf)+" %")
```

**K Cross Validation**


```python
#Logistic regression

from sklearn.model_selection import cross_val_score
from sklearn.model_selection import KFold
from numpy import mean
from numpy import std
logreg_kf = LogisticRegression()
cv = KFold(n_splits=5, random_state=100, shuffle=True)
scores = cross_val_score(logreg_kf, X, Y, scoring='accuracy', cv=cv, n_jobs=-1)
acc_lr = mean(scores)
print('Accuracy: %.3f' % (mean(scores)))
```


```python
#SVM
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import KFold
from numpy import mean
from numpy import std
svm_kf= svm.SVC(kernel='linear', C=1, gamma=1)
cv = KFold(n_splits=5, random_state=1, shuffle=True)
scores = cross_val_score(svm_kf, X, Y, scoring='accuracy', cv=cv, n_jobs=-1)
print('Accuracy: %.3f' % (mean(scores)))
```


```python
#knn
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import KFold
from numpy import mean
from numpy import std
knn_kf = KNeighborsClassifier(n_neighbors=7)
cv = KFold(n_splits=5, random_state=1, shuffle=True)
scores = cross_val_score(knn_kf, X, Y, scoring='accuracy', cv=cv, n_jobs=-1)
print('Accuracy: %.3f' % (mean(scores)))
```


```python
#decision Tree
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import KFold
from numpy import mean
from numpy import std
Dt_kf = DecisionTreeClassifier(max_depth=4, random_state=0)
cv = KFold(n_splits=5, random_state=1, shuffle=True)
scores = cross_val_score(Dt_kf, X, Y, scoring='accuracy', cv=cv, n_jobs=-1)
print('Accuracy: %.3f' % (mean(scores)))
```


```python
#Random Forest
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import KFold
from numpy import mean
from numpy import std
rf_kf = RandomForestClassifier(max_depth=5,n_estimators=100, random_state=5)
cv = KFold(n_splits=5, random_state=1, shuffle=True)
scores = cross_val_score(rf_kf, X, Y, scoring='accuracy', cv=cv, n_jobs=-1)
print('Accuracy: %.3f' % (mean(scores)))
```


```python
# initialize an empty list
accuracy = []

# list of algorithms names
classifiers = ['KNN','SVM','Logistic Regression', 'Naive Bayes','Decision Tress','Random forest']

# list of algorithms with parameters
models = [KNeighborsClassifier(n_neighbors=7),svm.SVC(kernel='linear', C=1, gamma=1),LogisticRegression(),
        GaussianNB(),DecisionTreeClassifier(max_depth=4, random_state=0),RandomForestClassifier(max_depth=5,n_estimators=100, random_state=5)]

# loop through algorithms and append the score into the list
for i in models:
    model = i
    model.fit(x_train, y_train)
    score = model.score(x_test, y_test)
    accuracy.append(score)
```


```python
summary = pd.DataFrame({'accuracy':accuracy}, index=classifiers)
summary

```

KNN	0.629630
SVM	0.777778
Logistic Regression	0.833333
Naive Bayes	0.740741
Decision Tress	0.759259
Random forest	0.796296


