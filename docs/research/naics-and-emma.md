# Phase 6 research: vendor NAICS codes (#18) and contract amendments via eMMA (#19)

**Date:** November 9, 2026. All endpoints and pages below were verified on this date unless noted.
**Scope:** decision-register items #18 (NAICS industry codes for vendors) and #19 (link contract amendments via eMaryland Marketplace contract awards).

## TL;DR

| Item | Verdict | Best path |
|---|---|---|
| #18 NAICS for vendors | **Feasible with registration** (SAM.gov, free key), plus **feasible now** partial coverage via USAspending (no key) | SAM.gov Entity Management API name matching, supplemented by USAspending MD-recipient bulk pull |
| #19 Contract amendments | **Blocked on eMMA for automation** (reCAPTCHA Enterprise browser check); **feasible now** via Board of Public Works agenda PDFs for contracts ≥ $200k | Parse BPW agendas; treat eMMA as manual spot-check only |

Neither opendata.maryland.gov nor any other state bulk source publishes NAICS codes or an eMMA award/amendment extract. Details below.

---

## 1. eMaryland Marketplace Advantage (eMMA) — emma.maryland.gov

### What eMMA is now (2025–2026 status)

"eMaryland Marketplace Advantage" **is** the modernization — it is the current, live production system (an Ivalua platform deployment), not a pending project. Evidence:

- The site's own CSS asset path contains the build stamp `buyer_maryland_V6_1_138_20261029` (i.e., a build dated 2026-10-29), so the platform is actively maintained.
- Towson University mandated eMMA registration for all vendors effective **September 1, 2025** (towson.edu/procurement/vendors.html), showing ongoing expansion of mandatory use across state entities in 2025.
- The Maryland Procurement Manual (procurement.maryland.gov, "most recent changes … effective 10/1/25") treats eMMA as the standing system of record for solicitations and award notices.

### Public, unauthenticated access — what I observed

Tested with curl on 2026-11-09:

| URL | Result |
|---|---|
| `https://emma.maryland.gov/` | HTTP 200 but redirects to `/page.aspx/en/usr/login?ReturnUrl=...` (login page) |
| `https://emma.maryland.gov/page.aspx/en/rfp/request_browse_public` (public solicitations) | HTTP 200 but lands on `/page.aspx/en/bas/browser_check` |
| `https://emma.maryland.gov/page.aspx/en/ctr/contract_browse_public` (public contracts) | Same — forced to `/page.aspx/en/bas/browser_check` |

The browser-check page contains a **reCAPTCHA Enterprise widget** (site key `6LcT1NUUAAAAAC0dOQWsG7KrikQDIgootx_fZzZz`, callback `verifyCaptchaEnterpriseCheckboxResponse`, action `browser_check`) and a `<noscript>` redirect to the login page. In plain terms:

- **Interactive human use:** public solicitation and contract browse pages are usable in a normal browser without an eMMA account (you pass the browser check, possibly with a checkbox challenge).
- **Automated/bulk access:** **blocked.** Any scraper must solve reCAPTCHA Enterprise per session; there is no public API, no bulk download, and no sitemap of awards. This is a deliberate anti-bot control, not a transient error.

### Does award data include NAICS codes and amendment history?

- **NAICS: no.** eMMA vendor profiles and solicitations are classified with **UNSPSC** commodity codes (Maryland Procurement Manual §1.4.1.1 and the eMMA Vendor User Guide: vendors "add … product and service categories using the United Nations Standard Products and Services Code (UNSPSC) codes"). NAICS is not part of the eMMA data model. Even with full access, eMMA cannot answer item #18.
- **Amendments:** two different things exist. *Solicitation* amendments are "Rounds" on the sourcing project (Vendor User Guide §6.6). *Contract* modifications live on the contract record; per the Vendor User Guide §6.7, "only awarded vendors can view their own contracts," i.e., the detailed contract record (with modification history) is **login-gated**. Award *notices* are required to be published in eMMA within 30 days of execution (Maryland Procurement Manual §7.3; COMAR 21.05.07.06 exempts small procurements from award reporting), and these notices are visible on the public browse pages — but bulk harvesting is blocked by the reCAPTCHA check above.

**Verdict for eMMA: blocked for automated data collection** (reCAPTCHA Enterprise browser check; no API; no bulk export). Manual, per-contract lookups in a browser are feasible for spot-checking individual vendors or awards. Note also that small-procurement awards are not required to be reported in eMMA at all (COMAR 21.05.07.06(J)(2), confirmed in the current Procurement Manual §3), so eMMA awards are not a complete population anyway.

---

## 2. SAM.gov (api.sam.gov)

### What it offers

The **Entity Management API** (`https://api.sam.gov/entity-information/v3/entities`, v1–v4) exposes, at the **Public** sensitivity level: legal business name, DBA, UEI, CAGE, addresses, business types, **`primaryNaics` and the full `naicsList`** (code + description + small-business flag), and PSC codes. Verified against the official documentation at open.gsa.gov/api/entity-api/ on 2026-11-09.

Useful query parameters for matching: `legalBusinessName` (**partial match supported**), `dbaName`, `physicalAddressProvinceOrStateCode=MD`, `stateOfIncorporationCode=MD`, `primaryNaics`, `registrationStatus`. Synchronous calls return 10 records/page and only the first 10,000 records; an **async Extract mode** (`format=csv|json`) returns a download link and can return up to 1,000,000 records.

### Registration and rate limits (official)

A free SAM.gov personal account is required; the "Public API Key" is issued from the Account Details page (OTP to email). Official rate limits (open.gsa.gov/api/entity-api/, "API Key Rate Limits"):

| Account type | Daily limit |
|---|---|
| Non-federal personal account, no role | **10 requests/day** |
| Non-federal personal account **with a role** (e.g., an entity registration) | **1,000 requests/day** |
| Non-federal system account | 1,000 requests/day |
| Federal system account | 10,000 requests/day |

I confirmed empirically that keyless and invalid-key calls to `api.sam.gov/entity-information/v3/entities` fail (HTTP 404, empty body) — a key is mandatory.

### Can Maryland payments vendors be matched by name?

Mechanically, yes: for each distinct payee in `7syw-q4cy`, call `?legalBusinessName=<payee>&physicalAddressProvinceOrStateCode=MD` and take the primary NAICS. **Coverage is the caveat:** SAM.gov only contains entities that registered for *federal* contracts/assistance (or were assigned a UEI). Maryland state-only vendors — small local firms, SBR-only suppliers — are largely absent. Expect partial coverage; measure the hit rate on the 4,478 multi-name vendor families before committing.

**Verdict: feasible with (free) registration.** Effort: ~0.5 day to register and prototype; ~1–2 days for a matching job with normalization, hit-rate measurement, and caching. The 10/day anonymous-account limit is too tight for ~9,686 payee names; either get a role-bearing account (1,000/day → about 10 days of lookups, cacheable) or pre-filter to the vendors that matter by dollar volume.

---

## 3. Maryland open data portal (opendata.maryland.gov)

Catalog API searches run 2026-11-09 (`api.us.socrata.com/api/catalog/v1?domains=opendata.maryland.gov&q=...`):

- `q=NAICS` → 27 results, **all employment-statistics projections by county** (e.g., `xzhk-d7hs`), none vendor- or contract-level.
- `q=contract award` / `q=procurement contract` / `q=eMMA` / `q=vendor` / `q=Board of Public Works` → nothing containing contract awards, amendments, or vendor NAICS. The only relevant dataset is the one the pipeline already uses (`7syw-q4cy`, payments), which has no NAICS or contract fields.

**Verdict: blocked — no such dataset exists on the portal.** If the state ever publishes an eMMA extract, this portal is where it would land; worth a quarterly re-check of the catalog search, one API call, trivial to automate.

---

## 4. DGS procurement reports / Board of Public Works (BPW)

### BPW action agendas — immediately usable public source (proof below)

BPW publishes every action agenda as a public PDF at predictable URLs (`https://bpw.maryland.gov/MeetingDocs/<YYYY-Mon-DD>-Agenda.pdf`, meetings roughly twice a month). Contracts above ~$200k require BPW approval, and — critically for #19 — **every modification/amendment above threshold also comes back to BPW as a `-MOD` item** with a structured template: Contract ID, EPICS/ADPICS number, Award (vendor), Original Contract Amount, Modification Amount, Prior Options/Mods (each with its own BPW item reference and date), Revised Total Contract Amount, and Percent Change.

**Proof** — extracted from `https://bpw.maryland.gov/MeetingDocs/2026-Apr-22-Agenda.pdf` (229 pages) with pypdf on 2026-11-09; verbatim field values:

| Item | Contract | Vendor (Award) | Original amount | Modification | Revised / change |
|---|---|---|---|---|---|
| DPSCS A1 | Kitchen Drain Repair, Baltimore Central Booking | The Drain Guys, LLC; Rockville, MD | $69,980 | $88,875 (this item) | $158,855; +127.00% |
| MDOT 6-E-MOD | High Volume Central Issuance Equipment Upgrade; V-HQ-15029-E; EPICS CO433503 | Thales DIS USA, Inc. (formerly Gemalto); Austin, TX | $3,543,559.86 | $325,980.00 (Mod. No. 8) | Prior mods listed individually: $431,986.00 (Mod. 1, DGS 4-E-MOD 03/28/2018); $1,655,398.36 (renewal, DGS 12-E-OPT 04/22/2020); $285,000.00 (Mod. 2, DGS 30-E-MOD 07/01/2020); $94,000.00 (Mod. 3 …) |
| MDOT 8-AE-MOD | Open-End Trackwork Engineering Services; AE-19-003-A/B/C/D; EPICS CO433794–97 | GFT Infrastructure / WSP USA JV, HNTB, AECOM (Baltimore, MD) | $7,000,000 NTE each ($28M aggregate) | $2,000,000 NTE each ($8M aggregate) | Prior: Mod. #1 $0.00 (amended work-order language, delegated authority MTA 10/01/2024) |
| MDOT 2-AE-MOD (Jul 22, 2026 agenda) | Miscellaneous Engineering Services; 522827B; ADPICS CO435408 | Johnson, Mirmiran & Thompson, Inc.; Hunt Valley, MD | $7,000,000 | $2,500,000 (Mod. No. 1) | Revised $9,500,000; +27.77% |
| MDOT 11-GM-MOD | MARC Ancillary Repairs; T-1987-0150-A–E; EPICS CO434156–57, CO434246–47, CO434280 | Amtrac Railroad Contractors of MD, Brawner Builders, Concrete Services, Delta-Railroad JV, Hawkeye Construction | $11.5M aggregate NTE (series) | +$3,500,000 | Revised $15,000,000 NTE |

That is amendment/modification history with dates, amounts, and cross-references — exactly what #19 asked eMMA for — in a bulk-downloadable, unauthenticated source.

**Limits:** only contracts that reach BPW (generally > $200k; the payments data has a long tail below that); PDFs are semi-structured text (layout varies by department), so parsing needs tolerant regexes and manual QA on a sample; no NAICS codes (this source is for #19, not #18).

### DGS statewide contract lists

procurement.maryland.gov/procurement-staff/ links to current statewide contract lists (Commodities/Maintenance/Construction "including Open Bids and Contract Awards", Professional Services, IT). These are public HTML/PDF lists of active statewide contracts with vendors — useful as a dimension table of current statewide awards, but not an amendment history and not bulk-friendly.

**Verdict: feasible now** via BPW PDFs. Effort: ~2–4 days — download schedule (predictable URLs), text extraction, per-department templates, and linking EPICS/ADPICS numbers and vendor names back to `ref.map_payee_vendor`. Ongoing cost is one cron-friendly fetch per meeting.

---

## 5. Bonus source found during research: USAspending.gov (no key, bulk, JSON)

Not in the original scope, but it is the only **immediately usable public bulk source with NAICS** found, so recorded here. `POST https://api.usaspending.gov/api/v2/search/spending_by_award/` is unauthenticated and returns per-award NAICS code + description for any recipient located in Maryland (federal awards only).

**Proof** — live call on 2026-11-09, filters: recipient state MD, award types A–D (contracts), CY2025, first 5 rows:

| Award ID | Recipient | Award amount | NAICS |
|---|---|---|---|
| W91ZRU26PA001 | NORRIS ACCOUNTING & TAX SERVICES, CPA LLC | $154,490.98 | 541219 — Other Accounting Services |
| W91ZRS25FA008 | GOVCONNECTION INC | $12,375.00 | 511210 — Software Publishers |
| W91ZLK26PA005 | CARON EAST, INC. | $30,000.00 | 811210 — Electronic and Precision Equipment Repair and Maintenance |
| W91ZLK25PA012 | ALPHA MOS AMERICA INC | $103,468.00 | 334516 — Analytical Laboratory Instrument Manufacturing |
| W91ZLK25P0039 | TENAX TECHNOLOGIES LLC | $85,881.60 | 541611 — Administrative Management and General Management Consulting Services |

This covers only state vendors that also hold federal contracts — a biased subset — but it costs nothing and can seed the NAICS mapping and calibrate the expected SAM.gov hit rate. (USAspending also has a bulk-download center and a recipient-profile API if fuller coverage is wanted.)

---

## Recommended implementation paths

**#18 NAICS for vendors — feasible with registration, partial coverage:**
1. (0.5 day) Create a SAM.gov personal account, request the Public API Key; prototype `entity-information/v3/entities` name matching on the top ~200 payees by dollar volume with `physicalAddressProvinceOrStateCode=MD`.
2. (0.5 day) In parallel, pull the USAspending MD-recipient contract set (no key) and name-match; this gives immediate partial coverage and a coverage estimate for SAM.gov.
3. (1 day) If the prototype hit rate justifies it, obtain a SAM.gov role for the 1,000/day tier (needs an entity registration; ~1–2 weeks lead time per SAM.gov guidance), then run the full payee list with caching into `reference/` (CSV with evidence, per the repo's change-control rules).
4. Leave unmatched vendors unclassified and show coverage % on the dashboard; do **not** fabricate NAICS from name heuristics.
Total: ~2–3 days of work plus lead time for the rate-limit upgrade. Coverage will be partial by construction — report it.

**#19 contract amendments — feasible now (partial, threshold-limited):**
1. (1 day) BPW agenda fetcher: predictable `MeetingDocs` URLs, pypdf extraction, tolerant templates for the `-MOD`/`-OPT` item format; store one row per (contract, modification) with BPW item references as citations.
2. (1–2 days) Link to payments via vendor name (`ref.map_payee_vendor`) and, where present, EPICS/ADPICS numbers; flag linked contracts in the vendor detail view.
3. Keep eMMA as a manual spot-check link (public pages work in a browser); do not build a scraper against the reCAPTCHA check.
Total: ~2–4 days. Coverage: BPW-threshold contracts only (>$200k); small procurements have no public amendment record anywhere (COMAR 21.05.07.06 reporting exemption).

## Sources verified (all 2026-11-09 unless noted)

- `https://emma.maryland.gov/` → login redirect; `/page.aspx/en/rfp/request_browse_public` and `/page.aspx/en/ctr/contract_browse_public` → reCAPTCHA Enterprise browser check (site key observed in page source).
- eMMA Vendor User Guide v2.0 (May 2022), procurement.maryland.gov — §6.6 Rounds, §6.7 "only awarded vendors can view their own contracts", UNSPSC classification.
- Maryland Procurement Manual §1.4.1.1, §3 (COMAR 21.05.07.06(J)(2) small-procurement reporting exemption), §7.3 (award notice in eMMA within 30 days), procurement.maryland.gov.
- open.gsa.gov/api/entity-api/ — Entity Management API endpoints, public NAICS fields, user requirements, official rate-limit table.
- api.sam.gov keyless/invalid-key calls → HTTP 404 (key mandatory).
- api.us.socrata.com catalog searches on opendata.maryland.gov — no NAICS/contract-award/eMMA/BPW datasets.
- bpw.maryland.gov/MeetingDocs/2026-Apr-22-Agenda.pdf and 2025-Oct-1/2026-Jul-22 agendas — modification-item structure and proof rows above.
- api.usaspending.gov/api/v2/search/spending_by_award/ — unauthenticated NAICS sample, rows above.
- towson.edu/procurement/vendors.html — eMMA registration mandatory from 2025-09-01 (modernization status).
