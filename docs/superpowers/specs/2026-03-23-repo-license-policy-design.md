# Repository License and Policy Docs Design

## Summary

This design defines a source-available licensing and repository policy structure for the
`0DTE Dealer Gamma Exposure (GEX) Monitor` project. The goal is to allow public access to
the source code for personal study, research, experimentation, noncommercial modification,
and noncommercial contributions, while withholding all commercial rights unless the
copyright holders grant them separately in writing.

The recommended public license is `PolyForm Noncommercial 1.0.0`, supplemented by
repository-level policy documents that clarify ownership, contribution expectations,
commercial licensing, support, and security reporting. The design also includes targeted
README fixes so the repository documentation matches the current codebase and license
positioning.

## Context

The repository is public on GitHub and the maintainers want to:

- allow people to study the code
- allow personal and non-profit, noncommercial use
- allow forks, modifications, and contributions for noncommercial purposes
- avoid separate contributor agreements that would add friction
- prohibit commercial use unless a separate written license is issued by the maintainers

The maintainers also want the ownership position to be stated clearly for `Puneet Chandna`
and `Gunjana Sahoo`.

## Goals

- adopt a standardized software license that allows noncommercial use, changes, and
  redistribution
- avoid custom legal drafting where a standardized license already fits the desired model
- make the commercial restriction prominent and easy to understand
- keep contribution flow simple by avoiding a separate CLA
- add standard repository policy documents that reduce ambiguity for users and contributors
- update the main README so setup instructions and license messaging reflect the actual repo

## Non-Goals

- creating an OSI-approved open source license
- inventing a custom legal license to replace a standardized software license
- guaranteeing perfect enforceability in every jurisdiction without attorney review
- restricting GitHub's platform-level ability to let users view and fork a public repository

## Recommended License Model

### Public License

Use `PolyForm Noncommercial 1.0.0` as the repository's software license.

Why this license:

- it is a software-specific standardized license rather than ad hoc custom wording
- it permits noncommercial use, modification, and distribution
- it is more aligned with the requested policy than MIT or Creative Commons
- it reduces ambiguity compared with inventing a bespoke "noncommercial code" license

### Commercial Rights

The public repository license should grant no commercial rights. Commercial use,
commercial hosting, monetized services, internal business use tied to revenue generation,
paid consulting or support based primarily on the software, and commercial derivatives
should require a separate written commercial license from the copyright holders.

This commercial path should be described in a separate repository document rather than by
editing the standard license text itself.

### Ownership Position

Ownership should be expressed as copyright ownership by:

- Puneet Chandna
- Gunjana Sahoo

The repository should avoid claiming exclusive ownership over third-party contributions
beyond what the repository license grants. Since no separate CLA will be used,
contributors retain ownership of their contributions while licensing those contributions
under the repository license when submitted.

## Legal Positioning and Terminology

The repository should consistently describe itself as:

- `source-available`, not `open source`
- available for noncommercial use under `PolyForm Noncommercial 1.0.0`
- commercially licensable only by separate written agreement

The repository should not claim:

- that it uses MIT
- that it is OSI open source
- that it is legally "airtight" in every jurisdiction

Instead, the docs should state that the maintainers selected a standardized noncommercial
software license and that users seeking commercial rights must contact the maintainers.

## Repository Documents

### `LICENSE`

Add the official, unmodified text of `PolyForm Noncommercial 1.0.0`.

Do not rewrite, shorten, or "improve" the license text. Standard license text should be
preserved exactly.

### `NOTICE`

Add a short notice file that:

- names the project
- names `Puneet Chandna` and `Gunjana Sahoo` as copyright holders
- includes the required notice line for downstream recipients
- points readers to the `LICENSE` file

This file gives the maintainers a clear ownership statement without trying to replace the
actual license terms.

The implementation should include a plain-text required notice line in the file so that
downstream users have concrete language to preserve with distributions.

### `COMMERCIAL-LICENSING.md`

Add a repository document explaining:

- the public repo license is noncommercial only
- no commercial rights are granted by the public repository license
- commercial use requires a separate written license
- inquiries should be sent to `puneetchandna21@gmail.com`
- examples of commercial use that require permission
- a direction that uncertain use cases should be treated as unlicensed until the user
  obtains written permission from the maintainers

Examples should be illustrative, not exhaustive. The document should avoid overpromising
that every scenario is fully resolved by examples alone.

### `CONTRIBUTING.md`

Add a contributing guide that:

- welcomes issues, fixes, and improvements
- states that by submitting a contribution, the contributor licenses it under the
  repository license
- states that no separate contributor license agreement is required
- explains that submitted contributions must be compatible with the repo's noncommercial
  licensing model
- sets expectations around code style, tests, and respectful collaboration

The file should not say that contributors assign ownership to the maintainers.

### `SECURITY.md`

Add a security policy that:

- asks reporters not to disclose vulnerabilities publicly before maintainers respond
- directs private reports to `puneetchandna21@gmail.com`
- states the type of information that helps triage a report
- gives a modest response expectation without overcommitting to SLAs

### `SUPPORT.md`

Add a support document that separates:

- community/help questions
- bug reports and feature requests
- security disclosures
- commercial licensing inquiries

This should reduce the chance that licensing questions end up buried in issues.

## README Changes

The main README should be updated alongside the license docs.

### Structural Improvements

- rename `Readme.md` to `README.md` for convention and discoverability
- add a visible "License and Commercial Use" section
- add links to `NOTICE`, `COMMERCIAL-LICENSING.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  and `SUPPORT.md`
- add a short note that the project is source-available rather than open source

### Accuracy Fixes

Based on the current repository snapshot, the README should be corrected to match the code:

- remove or revise the `Polygon.io` data-source reference if the project no longer uses it
- update setup instructions that currently reference missing
  `backend/.env.example` and `frontend/.env.example` files
- align the frontend test command with the actual script exposed by `frontend/package.json`
- consider documenting the top-level `.env.example` if that is the actual template in use

### Recommended Content Additions

If the edits remain modest, the README should also add:

- a short project status note
- a brief troubleshooting section
- a concise pointer to the docs already present in `docs/`

## Implementation Boundaries

This effort should remain documentation- and policy-focused. It should not:

- change application logic
- add legal claims unsupported by the chosen standardized license
- add a CLA workflow
- add issue templates unless needed to support the new policy docs

## Risks and Constraints

### GitHub Platform Constraint

Because the repository is public on GitHub, GitHub users can still view and fork the
repository through GitHub's platform functionality. The documentation should not imply that
the maintainers can forbid GitHub's platform-level public forking mechanics for a public
repository. The documentation should instead clarify that public GitHub visibility and
GitHub-native forking do not grant commercial rights beyond the repository license.

### Legal Constraint

No repository documentation should claim the license is guaranteed to be "airtight" or
free from all loopholes in every jurisdiction. The safer position is that the repository
uses a standardized noncommercial software license and that maintainers can obtain legal
counsel for jurisdiction-specific enforcement questions.

### Contribution Constraint

Without a separate CLA, outside contributors will normally own their own contributions
while licensing them under the repository license. The docs should make that workflow clear
and avoid contradictory language implying total ownership transfer to the maintainers.

## Acceptance Criteria

The design is successful if the repository ends up with:

- a standard `LICENSE` file using `PolyForm Noncommercial 1.0.0`
- a `NOTICE` file naming the maintainers
- `COMMERCIAL-LICENSING.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `SUPPORT.md`
- a corrected `README.md` that accurately describes licensing and setup
- consistent terminology that calls the repo `source-available`, not `open source`
- clear contact routing to `puneetchandna21@gmail.com`

## Research Basis

This design is based on:

- PolyForm Project documentation for `PolyForm Noncommercial 1.0.0`
- Creative Commons FAQ guidance against using CC licenses for software
- Open Source Initiative guidance that noncommercial restrictions are not open source
- GitHub Terms of Service regarding public repository visibility, forking, and
  contributions under repository license terms
