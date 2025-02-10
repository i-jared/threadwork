# THREADWORK

_Create software. Don't write it._

## Goal

Build human-grade software in one command.

## How it works

### Top level resources provided for agents:

- API & Key
- Function
  - description of app features and purpose
  - user stories
- Style:
  - example images, links
  - visual descriptions
  - component libraries
- Docs: The better the data in, the better the output
  - scraped and cleaned documentation for used technologies.
  - "brainlifts" or non-consensus ideas that you'd like incorporated into the software
  - TODO: create a scraper tool (like what cursor uses, most likely) to automatically grab and format docs

### Types of agents

- **planner**: takes an app description and decides how to structure it
- **expounder**: takes an app/feature explanation and breaks it out into minute detail
- **secretary**: takes a detailed description and breaks it up into distinct features/components
- **coder**: generates the code for a single feature/component

#### typical flow:

human description -> planner -> secretary -> expounder \* n -> [planner -> expounder ]\* -> [planner -> coder]

- auditor
- hr
- reviewer

#### things i need to code

- a generic way to call an api model
- generic agents that can take many actions and be connected in a DAG

**do we need business logic?**

- yes: route it to a business agent.
- no: ui only
  **do we need ui?**
- what
- is it small enough for one component?

### Tools provided to Agents

- doc review
  - look up the documentation provided for reference.
- command execution

## Usage

```bash
pip install -r requirements.txt
```

```python
print("Hello, world!")
```

## About

Created by Jared Lambert.
