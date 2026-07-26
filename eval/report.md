# RAG eval report

- Questions: 15
- Retrieval hit rate (must_contain term in retrieved contexts): 14/14 = 1.00
- RAGAS: {'faithfulness': 0.8278, 'answer_relevancy': 0.8274, 'context_utilization': 0.2317}

## Per-question scores

| user_input                                              |   faithfulness |   answer_relevancy |   context_utilization |
|:--------------------------------------------------------|---------------:|-------------------:|----------------------:|
| Which creators mention dry or damaged hair?             |       1        |           0.981162 |                 0     |
| Find comments showing intent to buy the product         |       1        |           0.870618 |                 0     |
| What do people say about heat damage?                   |       0.888889 |           0.870851 |                 0     |
| Which comments ask about price or restock?              |       1        |           0.819462 |                 0     |
| Summarize the buy-intent signals in the comments        |       0.5      |           0.774007 |                 0     |
| What are people saying about frizzy hair?               |       0.6      |           0.934336 |                 0     |
| Which comments mention a curly hair routine?            |     nan        |           0.87453  |                 0     |
| Do any comments mention split ends?                     |       1        |           0.916282 |                 0.25  |
| Are there comments about thinning hair?                 |       1        |           0.961803 |                 1     |
| Which creators are in the hair care category?           |       1        |           1        |                 0     |
| Do any commenters say they already ordered the product? |       1        |           0.967852 |                 0.225 |
| Which comments ask where to buy?                        |       1        |           0.929593 |                 0     |
| What categories do the creators fall into?              |       0.6      |           0.765621 |                 0     |
| What kinds of non-purchase engagement do videos get?    |       0.5      |           0.744204 |                 1     |
| What is the product's shipping policy?                  |       0.5      |           0        |                 1     |
