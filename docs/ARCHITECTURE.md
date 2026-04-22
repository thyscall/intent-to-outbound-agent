# Agentic Workflow Architecture

[Go back to the project README](../README.md)

```mermaid
graph TD
    A[Data Source: News API / RSS] -->|Raw Trigger Data| B(Agent 1: Signal Monitor)
    B -->|Filter: Is it a valid funding round?| C{Signal Valid?}
    C -->|No| D[Log & Terminate]
    C -->|Yes| E[Extract Company Context]
    
    E --> F(Agent 2: Account Researcher)
    F -->|Tool: Web Scraper / Apollo API| G[Identify target persona e.g., VP Sales]
    G --> H[Extract recent company news/initiatives]
    
    H --> I(Agent 3: Copywriter)
    I -->|Prompt: Sales Copywriting Framework| J[Draft highly personalized email]
    
    J --> K(Agent 4: QA Reviewer)
    K --> L{Passes strict tone/relevance QA?}
    L -->|No - Hallucination/Spammy| I
    L -->|Yes| M[Format JSON Payload]
    
    M --> N((Slack Webhook))
    N --> O[Human Rep Review & Send]
    
    classDef agent fill:#8B0000,stroke:#333,stroke-width:2px,color:#fff;
    class B,F,I,K agent;

