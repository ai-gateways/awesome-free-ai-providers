# Contribution Guidelines

Corrections and new providers are welcome, from both users and vendors. Free tiers change often, so a pull request that updates one limit with a link to the provider's page is as useful as a new entry.

## Ways to contribute

- **Open a pull request** to add, update, or remove an entry. An automated review comments within a few minutes.
- **Suggest a provider** with the [suggestion form](https://github.com/ai-gateways/awesome-free-ai-providers/issues/new?template=1-suggest-a-provider.yml) if you are not sure it fits or cannot edit the README yourself.
- **Report a change** with the [update form](https://github.com/ai-gateways/awesome-free-ai-providers/issues/new?template=2-update-an-entry.yml) when a limit changes, an offer ends, or a link breaks.

## What belongs here

- Hosted AI model APIs (language, embedding, rerank, speech, or image models) that give something away today: a permanent free tier, models offered at no cost, or a signup or trial credit.
- Cloud trial credits, when the cloud's own page says the credit can be spent on its generative AI service.
- Free models that only work in a provider's own client, when the provider also runs a public API. The entry says so.

Out of scope:

- Local runtimes and downloadable models with no hosted API.
- Consumer chat apps, IDEs, and coding assistants with no public API, and tools that reach them through scraping or reused logins.
- Relays that resell access to closed models from other vendors without a stated arrangement with those vendors.
- Services with no named operator in their terms, and offers that end within 30 days.

## Requirements for an entry

- **Every fact comes from the provider's own page.** Pricing, rate-limit, documentation, terms, and privacy pages count. Third-party lists, blogs, and aggregators do not, except for facts about the aggregator itself.
- **Link the exact section.** Use a heading anchor, or a `#:~:text=` fragment with exact words from the page when it has no anchors.
- **Link each page once.** awesome-lint treats two links to the same page as duplicates even when their anchors differ. When two facts come from one page, cite it once and write "per the pricing page" (or similar) in the other row.
- **Never guess.** If the provider does not publish a value, leave it out or write `Not published`. Do not test limits with an account and report what you saw.
- **Set the Verified date** to the day you checked the sources, on every entry you add or change.

Vendors are welcome to add or update their own entries. Disclose the connection in the pull request, and expect wording to be edited to stay neutral.

## Entry format

Each provider is a subsection in the section that matches its main free offer, in alphabetical order, plus one row in the At a Glance table.

```markdown
### Provider Name

One sentence that says what is free.

| Field             | Detail                                                  |
| ----------------- | ------------------------------------------------------- |
| Free              | What is free, with amounts and expiry ([source](link)). |
| Models            | Free models or model types ([source](link)).            |
| Limits            | Rate and usage limits, and what they apply to.          |
| Requires          | Account, card, phone, verification, or region rules.    |
| OpenAI-compatible | Yes, with the base URL, or No.                          |
| Data use          | Whether free-tier inputs may be used for training.      |
| Commercial use    | Only when the free offer restricts it.                  |
| Verified          | YYYY-MM-DD                                              |
```

- Keep the rows in this order. `Free` (with a source link) and `Verified` are required; leave out other rows the provider's pages do not cover.
- Add the At a Glance row in alphabetical order: `| [Provider Name](#provider-name) | Short offer | Card needed | OpenAI-compatible |`. Card needed is `Yes`, `No`, `Usually no`, or `Not stated`.
- If the provider publishes a token cap or a one-time token grant, add it to the totals in Combining Free Tiers.
- Write in US English with the Oxford comma. Skip slogans and superlatives, and do not use em dashes or en dashes.
- Use the provider's own units: RPM, RPD, TPM, TPD, credits, Neurons, minutes, or characters.
- Keep Chinese, Japanese, and Korean text out of the README; it breaks table alignment. Translate it, and keep the original only inside a link's URL.

## Updating an entry

1. Open every source link in the entry and compare each row with the page.
2. Change what moved, keeping one link per page, and add a source for any new fact.
3. Set `Verified` to today's date, even when nothing changed.
4. If the free offer ended, remove the entry and its At a Glance row, and link the page that shows it ended in the pull request.

## Pull requests

- Change one provider per pull request and fill in the pull request template, including your affiliation.
- Use a title such as `Add Name`, `Update Name limits`, or `Remove Name`.

## How pull requests are reviewed

1. **Automated review.** Within a few minutes, a bot comments on the pull request and labels it `needs changes` or `ready for review`. The comment updates on every push. It checks:
   - the heading, sentence, table header, row names and order, required rows, and the Verified date;
   - alphabetical order, duplicate entries, and the matching At a Glance row;
   - that no page is linked twice, and that there are no em dashes, en dashes, marketing words, or misaligned tables;
   - that every link loads and every section anchor or `#:~:text=` fragment exists on the page;
   - [awesome-lint](https://github.com/sindresorhus/awesome-lint#usage) on the whole list.
2. **Maintainer review.** A maintainer opens the sources and checks what a script cannot: that each row matches its page, that the offer is live and the operator is named, and that the wording is neutral.

A pull request cannot be merged until the automated review has no problems left to fix. Warnings do not block a merge. Some provider pages render with JavaScript or block automated requests, so the bot cannot confirm their anchors; a maintainer checks those by hand.

### Check your entry locally

The checker needs only Python 3.9 or later:

```sh
python3 .github/scripts/review.py format README.md
python3 .github/scripts/review.py check README.md
python3 .github/scripts/review.py check README.md --network
```

The first command lines up the table pipes. The second runs the format, order, and duplicate checks. The third also loads every link and checks its anchor, which takes about a minute. Add `--lint` to run awesome-lint as well (needs Node.js).

## Keeping the list current

A scheduled job rechecks the whole list every Monday. It opens or updates a `List health report` issue when a link breaks, an anchor moves, an entry's Verified date is more than 90 days old, or an offer's stated end date has passed. Picking an entry from that issue and re-checking it is a good first contribution.
