# RAG eval report

- Questions: 18
- **Answer quality:** faithfulness, answer_relevancy
- **Retrieval quality:** context_precision (relevant contexts ranked high), context_recall (all needed context retrieved) — both vs. an authored ground truth
- Lexical retrieval recall (free, non-LLM — must_contain term present in retrieved contexts): 16/17 = 0.94
- RAGAS: {'faithfulness': 0.8459, 'answer_relevancy': 0.7194, 'context_precision': 0.4818, 'context_recall': 0.3889}

## Per-question scores

| user_input                                                        |   faithfulness |   answer_relevancy |   context_precision |   context_recall |
|:------------------------------------------------------------------|---------------:|-------------------:|--------------------:|-----------------:|
| Which creators mention dry or damaged hair?                       |       1        |           0.936456 |            0.333333 |                1 |
| Find comments showing intent to buy the product                   |       0.95     |           0.838311 |            0        |                0 |
| What do people say about heat damage?                             |       1        |           0.730916 |            0.369444 |                0 |
| Which comments ask about price or restock?                        |       0.222222 |           0.748909 |            0.45     |                0 |
| Summarize the buy-intent signals in the comments                  |       1        |           0.798409 |            0        |                0 |
| What are people saying about frizzy hair?                         |       0.894737 |           0.73359  |            0.402778 |                1 |
| Which comments mention a curly hair routine?                      |       0.846154 |           0.793667 |            0.82602  |                0 |
| Do any comments mention split ends?                               |       1        |           0.94432  |            1        |                1 |
| Are there comments about thinning hair?                           |       1        |           0.801741 |            0.416667 |                0 |
| Which creators are in the hair care category?                     |       0.777778 |           1        |            1        |                0 |
| Do any commenters say they already ordered the product?           |       0.933333 |           0.887093 |            1        |                1 |
| Which comments ask where to buy?                                  |       1        |           0.813032 |            0        |                0 |
| What categories do the creators fall into?                        |       1        |           0.938799 |            0        |                1 |
| What kinds of non-purchase engagement do videos get?              |       0.875    |           0.629857 |            0        |                0 |
| Which creators should we sample next for the Detangler Pro Brush? |     nan        |           0        |            0.625    |                0 |
| What watchouts do the top-ranked creators have?                   |       1        |           0.729556 |            0.25     |                0 |
| Which creators have strong buy-intent signals in their audience?  |       0.681818 |           0.624646 |            1        |                1 |
| What is the product's shipping policy?                            |       0.2      |           0        |            1        |                1 |
