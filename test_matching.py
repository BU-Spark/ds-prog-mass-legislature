with open("bill_text.txt", "r", encoding="utf-8") as f:
    bill_text = f.read()

with open("FY27_final_budget_text.txt", "r", encoding="utf-8") as f:
    budget_text = f.read()

words = ["chapter 70", "inflation"]

budget = " ".join(budget_text.lower().split())

#comparing some words and phrases from S.388 with the budget bill 
for word in words: 
    if word in budget:
        print(f"'{word}' found in budget text.")
    else:
        print(f"'{word}' not found in budget text.")

keyword = "chapter 70"
start_pos = 0
count = 0

while True:
    position = budget.find(keyword, start_pos)
    if position == -1:
        break
    count += 1

    print(f"'{keyword}' found {count} times")

    start = max(0, position - 150)
    end = position + 250
    print(budget[start:end])

    start_pos = position + len(keyword)

#found the number of occurrences of the keyword in the budget 
print(f"Total occurrences of '{keyword}': {count}")

#the output of the above found 19 occurrences of "chapter 70" if i used the FY27_budget_text
#in the budget but most was related to school funding amount
#rather than specific language in S.388 but it does show the 
#budget is related to the bill and talks about the same topic 

#if i use the final27 budget it found some specific phrase from S.388
phrases = ["foundation inflation index", "foundation allotments", "foundation category"]
for phrase in phrases:
    count = budget.count(phrase)
    print(f"'{phrase}' found {count} times in budget text.")

print("Foundation in S.388:", "foundation" in bill_text.lower())
print("Foundation in budget:", "foundation" in budget_text.lower())