# RAG eval report

- Questions: 18
- Retrieval hit rate (must_contain term in retrieved contexts): 16/17 = 0.94
- RAGAS: {'faithfulness': 0.8200, 'answer_relevancy': 0.7377, 'context_utilization': 0.0829}

## Per-question scores

| user_input                                                        |   faithfulness |   answer_relevancy |   context_utilization |
|:------------------------------------------------------------------|---------------:|-------------------:|----------------------:|
| Which creators mention dry or damaged hair?                       |     nan        |           0.959385 |              0        |
| Find comments showing intent to buy the product                   |       0.923077 |           0.645142 |              0        |
| What do people say about heat damage?                             |       0.833333 |           0.676041 |              0        |
| Which comments ask about price or restock?                        |     nan        |           0.736636 |              0        |
| Summarize the buy-intent signals in the comments                  |     nan        |           0.549931 |              0        |
| What are people saying about frizzy hair?                         |     nan        |           0.852667 |              0        |
| Which comments mention a curly hair routine?                      |       0.818182 |           0.879264 |              0        |
| Do any comments mention split ends?                               |       1        |           0.942419 |              0        |
| Are there comments about thinning hair?                           |       0.923077 |           0.795674 |              0        |
| Which creators are in the hair care category?                     |       1        |           1        |              0        |
| Do any commenters say they already ordered the product?           |       1        |           0.885583 |              0.366667 |
| Which comments ask where to buy?                                  |       1        |           0.591561 |              0        |
| What categories do the creators fall into?                        |       0.818182 |           0.70527  |              0        |
| What kinds of non-purchase engagement do videos get?              |       0.857143 |           0.66317  |              0        |
| Which creators should we sample next for the Detangler Pro Brush? |       0.333333 |           0.857858 |              0.125    |
| What watchouts do the top-ranked creators have?                   |     nan        |           0.850955 |              0        |
| Which creators have strong buy-intent signals in their audience?  |     nan        |           0.687885 |              0        |
| What is the product's shipping policy?                            |       0.333333 |           0        |              1        |
