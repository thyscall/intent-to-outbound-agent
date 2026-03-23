# Autonomous GTM Agent

This is an autonomous system built with LangChain and CrewAI that uses AI agents to constantly be on the lookout for high-intent buying signals, research the right people to talk to, and draft personalized outreach emails.
I wanted to build something that handles the heavy lifting of lead research without a human needing to click every button. The goal is to create a system that acts as a partner to a sales team by finding the best opportunities and doing the dirty work so they can focus on the human side of the business.

## Project Scope

This project is a multi-agent system designed to automate the initial stages of the outbound sales motion. The workflow utilizes four specific agent roles:

* **Signal Monitor:** Scans external data sources like Clay for specific company-level trigger events.
* **Account Researcher:** Identifies target personas within the signaled companies and compiles relevant background data using Apollo and BeautifulSoup
* **Copywriter:** Drafts targeted outreach messaging based on the signal and persona research.
* **QA Reviewer:** Evaluates the drafted text against strict criteria for relevance and tone. This enforces a self-correction loop before final output.

The system concludes by formatting the data and delivering it via Slack for human review and approval.

## Business Intent

Revenue operations and sales teams process large volumes of data to find qualified leads. Standard intent platforms deliver raw lists of companies showing generic activity. Sales representatives must manually research these companies to find the correct contacts and understand the context before writing an email. 

This system automates the research and drafting phases. By providing a verified signal, a researched contact, and a prepared draft, it allows sales professionals to allocate their time to direct prospect engagement.

## Architecture

View the architecture diagram in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Tech Stack

* **Languages & Frameworks:** Python, LangChain, CrewAI
* **AI:** OpenAI API
* **GTM Tools & APIs:** Clay, Apollo, BeautifulSoup, and Salesforce/HubSpot developer docs
* **Communication:** Slack webhooks

## Project Structure

autonomous_gtm_agent/
│
├── shared/
│   ├── crm_client.py
│   └── schemas.py
│
├── autonomous_sdr/
│   ├── agent_monitor.py     
│   ├── agent_researcher.py
│   ├── agent_copywriter.py
│   ├── agent_reviewer.py
│   ├── tool_clay.py
│   ├── tool_apollo.py
│   ├── main.py
│   └── README.md
│
├── docs/
│   ├── ARCHITECTURE.md
│   └── PROPOSAL.md
│
└── README.md


## Documentation & Technical Challenges

[Placeholder: Link to detailed documentation, local setup instructions, and a summary of technical roadblocks overcome during development]

## Demo & Resources

* [Placeholder: Link to video demo]
* [Placeholder: Link to article or post]
