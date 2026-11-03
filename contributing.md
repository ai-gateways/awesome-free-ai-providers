# Contribution Guidelines

Corrections and new providers are welcome, from both users and vendors. Free tiers change often, so a pull request that updates one limit with a link to the provider's page is as useful as a new entry.

## What belongs here

- Hosted AI model APIs (language, embedding, rerank, speech, or image models) that give something away today: a permanent free tier, models offered at no cost, or a signup or trial credit.
- Cloud trial credits, when the cloud's own page says the credit can be spent on its generative AI service.

Out of scope:

- Local runtimes and downloadable models with no hosted API.
- Consumer chat apps, IDEs, and coding assistants with no public API, and tools that reach them through scraping or reused logins. Free models that only work in a provider's own client are listed when the provider also runs a public API, and the entry says so.
- Relays that resell access to closed models from other vendors without a stated arrangement with those vendors.
- Services with no named operator in their terms, and offers that end within 30 days.

## Requirements for an entry

- **Every fact comes from the provider's own page.** Pricing, rate-limit, documentation, terms, and privacy pages count. Third-party lists, blogs, and aggregators do not, except for facts about the aggregator itself.
- **Link the exact section.** Use a heading anchor, or a `#:~:text=` fragment when the page has no anchors.
- **Link each page once.** awesome-lint treats two links to the same page as duplicates even when their anchors differ. When two facts come from one page, cite it once, in the row it backs best.
- **Never guess.** If the provider does not publish a value, leave it out or write `Not published`. Do not test limits with an account and report what you saw.
- **Update the Verified date** of every entry you check, even when nothing changed.

Vendors are welcome to add or update their own entries. Disclose the connection in the pull request, and expect wording to be edited to stay neutral.

## Entry format

Each provider is a subsection in the section that matches its main free offer, kept in alphabetical order, plus one row in the At a Glance table.

```markdown
### Provider Name

One sentence that says what is free.

| Field             | Detail                                                    |
| ----------------- | --------------------------------------------------------- |
| Free              | What is free, with amounts and expiry ([source](link)).   |
| Models            | Free models or model types ([source](link)).              |
| Limits            | Rate and usage limits, and what they apply to.            |
| Requires          | Account, card, phone, verification, or region rules.      |
| OpenAI-compatible | Yes, with the base URL, or No.                            |
| Data use          | Whether free-tier inputs may be used for training.        |
| Verified          | YYYY-MM-DD                                                |
```

- Leave out a row that the provider's pages do not cover, except Free and Verified.
- Write in US English with the Oxford comma. Skip slogans and superlatives, and do not use em dashes or en dashes.
- Use the provider's own units: RPM, RPD, TPM, TPD, credits, Neurons, minutes, or characters.

## Check your change locally

awesome-lint needs the pipes in every table to line up. Prettier aligns them:

```sh
npx prettier --write README.md
npx awesome-lint
```

## Pull requests

- Use a title such as `Add Name`, `Update Name limits`, or `Remove Name`.
- To remove an entry, link the page that shows the free offer ended.
