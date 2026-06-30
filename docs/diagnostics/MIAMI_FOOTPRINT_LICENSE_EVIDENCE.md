# Miami-Dade Building Footprint License Evidence

**Branch:** `research/miami-footprint-license-v1`
**Base commit:** `7b6be7fb77a66291c4500760e39c5cc23ee6495a`
**Research date:** 2026-06-30
**Researcher role:** Footprint-license evidence research only — documentation, no code/config changes.
**Scope constraint:** No modification of `production_allowed`, `REAL_DATA_EXECUTION_ENABLED`, or any
pipeline authorization flag. No data upload. No claim that the license is resolved.

A prior independent audit on a sibling branch (`research/miami-footprint-license`, base
`6a5dabb9a0f82121b307cfb18ac04b390d3f8415`) reached the same dataset identity and the same
overall disposition (`LICENSE NOT CONFIRMED`) from the same primary sources. That audit is
preserved at `docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md`. This document is an
independently re-fetched and re-verified evidence record, structured per the dimensions required
for this research instance, and adds one dimension that prior audit could not resolve
(cloud-storage / cloud-processing implications).

---

## 1. Dataset Owner and Publisher

| Field | Value | Source |
|---|---|---|
| Dataset title | Building Footprint 2D | S1, S2 |
| Owning government | Miami-Dade County, Florida (a county government, not a city, state, or federal agency) | S1 |
| Publishing department | Miami-Dade County Information Technology Department (ITD), Geospatial Infrastructure Support Group | S1, S3 |
| ArcGIS Online publisher account | `MDPublisher` (org ID `8Pc9XBTAsYuxx9Ny`) | S1 |
| ArcGIS Item ID | `d511e9ebc5aa4f49a23ff5fa2fb99786` | S1 |
| Item status | `public_authoritative` | S1 |
| FeatureServer | `https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer` (Layer 0) | S2 |
| Public dataset pages | `https://gis-mdc.opendata.arcgis.com/datasets/MDC::building-footprint-2d/about` and `https://opendata.miamidade.gov/datasets/MDC::building-footprint-2d/about` (same item, two portal aliases) | S1, S4 |
| Created / modified | June 14, 2018 / January 1, 2025 (per ArcGIS item) — modification date differs slightly across endpoints (S1: Jan 1 2025; S2: August 2024); not material to license analysis | S1, S2 |
| Current feature count | 863,196 | S1, S2 |

**CONFIRMED FACT:** The dataset is owned and published by Miami-Dade County government itself
(via its own ArcGIS Online organizational account), not by a third-party data broker or a
different jurisdiction.

---

## 2. Official Terms of Use

The only terms-of-use text attached to the dataset item (`licenseInfo` field, confirmed
identically via two independent endpoints — the ArcGIS Sharing REST API and the ArcGIS Hub v3
API) is:

> "Miami-Dade County provides this data for use 'as is'. The areas depicted by this map/data
> are approximate, and are not accurate to surveying or engineering standards. The maps/data
> shown here are for illustration purposes only and are not suitable for site-specific decision
> making. Information found here should not be used for making financial or any other
> commitments. Miami-Dade County provides this information with the understanding that it is
> not guaranteed to be accurate, correct or complete and conclusions drawn from such information
> are the sole responsibility of the user. While every effort has been made to ensure the
> accuracy, correctness and timeliness of materials presented, Miami-Dade County assumes no
> responsibility for errors or omissions, even if Miami-Dade County is advised of the
> possibility of such damage."

License type designation on the Hub dataset page: **"Custom"** (no Creative Commons or public-domain
badge applied). (S1, S2)

The portal-wide **"Open Data Policy"** page exists at both
`https://gis-mdc.opendata.arcgis.com/pages/open-data-policy` and (mirrored on the newer portal
domain) `https://opendata.miamidade.gov/pages/open-data-policy`, but its body content is
rendered client-side by JavaScript and could not be retrieved by any fetch method attempted in
this research session (direct fetch, Wayback Machine, search-engine cache, DCAT feed). This was
also true in the prior independent audit. **Its content remains unknown.** (S5 — attempted,
unresolved)

**CONFIRMED FACT:** The only verifiable terms governing this specific dataset are the
"as-is"/accuracy-disclaimer paragraph above. It is a liability and accuracy disclaimer, not an
affirmative license grant (it does not name a license such as CC0, CC BY, or Public Domain) and
does not contain the words "license," "permit," "prohibit," "commercial," or "redistribute."

**UNRESOLVED:** Whether the separate, inaccessible Open Data Policy page adds any term (license
grant, restriction, or attribution requirement) that is not present in the per-dataset text.

---

## 3. Commercial-Use Rights

**No document obtained in this research grants or denies commercial use explicitly for this
dataset.** The per-item disclaimer is silent on commercial use.

Independent legal context (not dataset-specific, but governing Florida county records generally):

- Florida Statute § 119.01(1)–(2): "All state, county, and municipal records are open for
  personal inspection and copying by any person," subject to "the restrictions of copyright and
  trade secret laws and public records exemptions." Verbatim text confirmed by direct fetch of
  the Florida Legislature statute page on 2026-06-30. (S6)
- Florida Attorney General Opinion 2003-42 (Sept. 2, 2003), addressing Palm Beach County's
  attempt to license/restrict GIS map redistribution: "In the absence of a statute authorizing
  the county to restrict the use of these public records by requiring license agreements for
  its Geographic Information Systems maps and related data, the county does not possess such
  authority," and "Palm Beach County is not authorized to obtain copyright protection and
  require license agreements for its [GIS] maps and related data in order to regulate and
  authorize redistribution of these materials for commercial use." This opinion also notes that
  to the extent the county holds copyrighted work received from others in connection with county
  business, federal copyright law governs that material independently. Confirmed via search-engine
  cached extract after direct fetch returned HTTP 403; full opinion is publicly indexed at
  `myfloridalegal.com/ag-opinions/records-license-agreements-for-county-maps`. (S7)

**REASONABLE INTERPRETATION, NOT A CONFIRMED RIGHT:** AGO 2003-42 is persuasive, not binding, on
Miami-Dade County (it was issued for Palm Beach County), and it is an Attorney General opinion,
not a statute or court ruling. It supports — but does not by itself establish — that Miami-Dade
County itself lacks authority to restrict commercial redistribution of its own GIS records. It
does **not** resolve whether material originating from a third-party contractor and incorporated
into the county's dataset is "the county's own record" for this purpose (see Section 6).

---

## 4. Copying and Redistribution Rights

- Downloading is structurally permitted: the FeatureServer exposes `capabilities: "Query,Extract"`
  with anonymous access and no authentication wall, confirmed by direct fetch of the FeatureServer
  JSON on 2026-06-30. `copyrightText` on the FeatureServer is an empty string. (S2)
- The general ArcGIS Online terms-of-use documentation states that for publicly shared content,
  "the specific terms of use for content items are provided in the terms of use for that
  content," that it is the user's responsibility to abide by the content owner's stated terms,
  and that "if an item description does not contain information about terms of use, you can
  assume there are no special restrictions or limitations on using the content." (S8, S9) Because
  this item *does* contain stated terms (the disclaimer in Section 2), that default-permissive
  fallback does not independently apply here — the disclaimer is the operative term, and it does
  not address redistribution one way or the other.
- Florida § 119.01 establishes a right to copy public records generally (Section 3 above).

**CONFIRMED FACT:** Bulk download, local storage, and use of the FeatureServer/Hub export is not
gated by any technical or stated contractual restriction discovered in this research.

**UNRESOLVED:** Whether *redistributing* the raw or lightly-transformed footprint dataset
(as opposed to internal use) to end users of a commercial product is affirmatively permitted.
No document says yes; no document says no. The Florida public-records right to "copy" is
documented for inspection/copying generally, not specifically validated against republishing
inside a commercial software product.

---

## 5. Derivative-Work Rights

No document obtained — dataset-level, portal-level, or statutory — explicitly addresses creating
or publishing derivative works (clipped tiles, reprojected geometry, extruded 3D building masses,
rendered scenes) from this footprint dataset.

**UNRESOLVED:** Whether 3D building masses extruded from this footprint geometry (combined with
independently public-domain LiDAR height data) constitute a permitted derivative use of the
footprint geometry, or a use requiring separate permission. No affirmative license clause (e.g.,
"derivative works permitted with attribution") exists for this dataset to answer this question
either way.

---

## 6. Contractor or Third-Party Rights

The ArcGIS item description states the dataset "derives from 2018 GPI LiDAR with 2021 Woolpert
updates," and identifies ESRI as the contractor that executed a planimetric update under county
contract (contract number referenced in metadata as BW8207-2/12). (S1, prior-audit cross-check S2
from the sibling research branch)

Three private firms are named in the data lineage: **GPI** (2018 LiDAR collection/extraction),
**Woolpert** (2021 planimetric update), and **ESRI** (planimetric update execution).

**PROHIBITED ASSUMPTION:** It must not be assumed that Miami-Dade County holds unrestricted,
assignable copyright in 100% of this dataset merely because the county publishes it. Under U.S.
copyright law, work product created by an independent contractor is not automatically a
"work made for hire" — title remains with the contractor absent a written assignment or
qualifying work-for-hire agreement. No such assignment document was located in any source
reviewed in this research.

**UNRESOLVED (CRITICAL):** Whether Miami-Dade County obtained a full rights assignment from GPI,
Woolpert, and/or ESRI sufficient to grant the public (and, more specifically, a commercial
downstream redistributor) unrestricted use of the planimetric data those contractors produced.
AGO 2003-42 itself flags this exact category of risk: copyrighted material the county "may
receive... in connection with its official business" remains independently governed by federal
copyright law. (S7) This is the single largest open item blocking a CONFIRMED disposition.

---

## 7. Attribution Requirements

No attribution requirement is stated as a condition of use anywhere in the dataset's terms.
The FeatureServer `copyrightText` field is empty. (S2)

The ArcGIS item's `accessInformation` (credit) field reads: **"Miami-Dade County ITD -
Geospatial Infrastructure Support Group."** (S1) This is a metadata credit field, not contractual
language requiring downstream attribution.

**CONFIRMED FACT:** No mandatory attribution clause was found.

**RECOMMENDED (not a confirmed legal requirement):** Carry the credit line above plus a link to
the dataset page in any product documentation or legal-notices file, both as good practice and
to avoid any implication of false sourcing — pending the Open Data Policy text, which might
impose a formal requirement not currently visible.

---

## 8. Disclaimer and Warranty Terms

Fully covered by the verbatim text in Section 2: data is "as is," approximate, not
survey/engineering grade, "for illustration purposes only," "not suitable for site-specific
decision making," not to be used for "financial or any other commitments," and the county
disclaims warranty of accuracy/completeness and liability for errors or omissions, including
consequential damages, even if the county was advised of the possibility of such damage. (S1, S2)

**CONFIRMED FACT:** This is the complete disclaimer; no separate or more permissive warranty
language was found at any other endpoint checked.

---

## 9. Cloud-Storage or Cloud-Processing Implications

This dimension was not resolved in the prior sibling audit. This research attempted it directly
and the result is **inconclusive**, not negative or positive:

- General ArcGIS Online public-item terms documentation states the content owner's stated terms
  govern public content, and that absent stated restrictions, "you can assume there are no
  special restrictions." (S8) Nothing in that general documentation singles out third-party cloud
  storage (e.g., AWS/Azure/GCP) of downloaded public Hub data as separately restricted.
- A separate Esri commercial document (one of the "Esri Master Agreement" family, e.g. E204/E204CW
  product-specific terms) was located, and an automated summary of it described provisions
  restricting "scraping, downloading, or storing" certain **Esri-owned content/services**
  (e.g., Living Atlas, Business Analyst, bundled basemap "Content Packages") delivered to
  *licensed ArcGIS subscription customers*, plus general anti-redistribution language for
  Esri Software/Online Services access. **This document could not be independently verified
  against its actual PDF text in this session** (the fetch tool returned only an index page and
  produced a model-generated summary of linked-but-unfetched PDFs). It is unclear, and was not
  confirmed, whether that Master Agreement family governs:
  (a) anonymously-accessible, publicly-shared **government open data** hosted by a county on its
      own ArcGIS Online organizational account (the case here), as opposed to
  (b) Esri's own proprietary content/services delivered under a paid ArcGIS subscription.
  These are very plausibly different things, but this research could not conclusively confirm
  that distinction from primary text.

**UNRESOLVED (do not rely on either direction):** Whether any Esri platform-level agreement
imposes a restriction — independent of Miami-Dade County's own terms — on extracting this
FeatureServer's data via automated/bulk requests and storing or processing it on third-party
cloud infrastructure as part of a commercial pipeline. This must be confirmed either by obtaining
and reading the actual current Esri Master Agreement / Product-Specific Terms PDF in full, or by
written confirmation that the relevant terms do not apply to anonymous access of county-published
Open Data Hub content.

**PROHIBITED ASSUMPTION:** Do not assume cloud processing is unrestricted merely because the
FeatureServer is reachable without authentication, and do not assume cloud processing is
prohibited based on the unverified Master Agreement summary above. Neither has been confirmed.

---

## 10. Publication of Transformed Geometry and Derived Attributes

No document obtained states this affirmatively or negatively for this dataset. Relevant
distinctions surfaced by this research:

| Output | Status |
|---|---|
| Calculated/measured attributes derived primarily from independently public-domain LiDAR (e.g., building height, roof characteristics) | Reasonably interpreted as low-risk — not dependent on footprint-geometry copyright status |
| Footprint geometry itself, reprojected/clipped/simplified | UNRESOLVED — no restriction found, but no affirmative grant found either |
| Footprint-derived calculated geometric attributes (area, perimeter) | UNRESOLVED — geometry-dependent |
| Extruded 3D masses, rendered scenes, GLB tiles built on footprint geometry | UNRESOLVED — the dataset's terms do not address derivative 3D products; this is the actual GlitchOS use case and the one most exposed to the unresolved contractor-copyright question in Section 6 |

**Do not infer that publication of transformed geometry is authorized merely because the source
file is downloadable without a login wall.** That fact establishes access, not republication
rights.

---

## 11. Official Agency Contact for Written Clarification

| Channel | Value | Source |
|---|---|---|
| Primary GIS contact email | **gis@miamidade.gov** | S1, S3, S10 |
| Publishing department | Miami-Dade County ITD — Geospatial Infrastructure Support Group | S1 |
| General department line | Communications, Information and Technology Department, 305-596-8200 | S10 |
| Mailing address | Stephen P. Clark Center, 111 NW 1st Street, Miami, FL 33128 | S10 (search-indexed) |

`gis@miamidade.gov` is the correct first point of contact: it is the contact address embedded
directly in the dataset's own ArcGIS item metadata, not a generic county switchboard. If ITD
cannot speak to the contractor-copyright assignment question (Section 6), the next escalation
point is the Miami-Dade County Attorney's Office, which was not directly contacted or verified
in this research.

---

## 12. Confirmed Rights

1. Miami-Dade County government (via its own ArcGIS Online org) is the publisher and stated
   data owner of the "Building Footprint 2D" dataset, Item ID `d511e9ebc5aa4f49a23ff5fa2fb99786`.
2. The complete operative license text is the "as is" accuracy/liability disclaimer quoted in
   Section 2 — verbatim, independently confirmed via two API endpoints.
3. Public, unauthenticated download/extract access to the dataset is permitted by the service's
   own declared capabilities (`Query,Extract`) and by Florida § 119.01's general public-records
   copying right.
4. No mandatory attribution clause is attached to the dataset; a credit field
   ("Miami-Dade County ITD - Geospatial Infrastructure Support Group") exists but is metadata,
   not a contractual condition.
5. No explicit prohibition on commercial use, redistribution, or derivative works is stated
   anywhere this research could access.
6. Florida law constrains the *county's own* ability to impose license restrictions on its own
   GIS records (AGO 2003-42), though this does not resolve the contractor question.

## 13. Unresolved Rights

1. Whether contractor-produced (GPI, Woolpert, ESRI) planimetric data within the dataset was
   fully assigned to the county such that downstream commercial redistribution and derivative
   use carry no third-party infringement exposure. **(Critical — Section 6.)**
2. The full content of the Open Data Policy page (`/pages/open-data-policy`) on both portal
   domains — never retrieved, by this research or the prior sibling audit.
3. Whether Esri platform-level agreements impose any additional restriction on bulk/automated
   extraction and third-party cloud storage/processing of this specific publicly-shared dataset.
4. Whether redistribution of derived 3D geometry (extruded building masses, GLB tiles, rendered
   scenes) built from this footprint geometry is within the scope of rights Florida law grants
   for "copying" public records, or requires separate permission.
5. Whether AGO 2003-42 (issued for Palm Beach County) has ever been formally adopted, contested,
   or narrowed by Miami-Dade County specifically.

## 14. Prohibited Assumptions

1. Do not assume the dataset is public domain or unrestricted merely because it is freely
   downloadable without login. Access rights and republication rights are legally distinct
   questions.
2. Do not assume the county holds full, assignable copyright over 100% of the dataset's content
   merely because the county is the publisher of record.
3. Do not assume the absence of a stated commercial-use prohibition is equivalent to an
   affirmative commercial-use grant for redistribution of derivative 3D products specifically.
4. Do not assume Esri's general ArcGIS Online platform terms either permit or restrict
   third-party cloud storage/processing of this dataset — that specific question is unverified
   in both directions.
5. Do not assume AGO 2003-42's conclusion (about Palm Beach County's own authority) automatically
   extends to resolve Miami-Dade County's contractor-rights question — it does not address that
   question and, if anything, flags it as a live exception.
6. Do not set `production_allowed: true` or change `footprint_source.license` away from
   `open_data_terms_unconfirmed` based on this document alone.

## 15. Exact Questions Requiring Written Agency Confirmation

To be sent to **gis@miamidade.gov**, referencing the dataset by name ("Building Footprint 2D,"
Item ID `d511e9ebc5aa4f49a23ff5fa2fb99786`):

1. "For the planimetric/building-footprint data contributed by GPI (2018) and Woolpert (2021)
   under county contract, did Miami-Dade County obtain a full assignment of rights or a
   work-for-hire acknowledgment from these contractors covering public commercial
   redistribution and derivative-work use of the resulting data? Can the County confirm in
   writing that no contractor retains rights that would restrict downstream commercial use?"
2. "Does the Open Data Policy referenced at `gis-mdc.opendata.arcgis.com/pages/open-data-policy`
   (and/or `opendata.miamidade.gov/pages/open-data-policy`) impose any terms — commercial-use
   conditions, attribution requirements, or redistribution restrictions — beyond the per-dataset
   'as is' disclaimer shown on the Building Footprint 2D item page? Can the County provide the
   full text of that policy?"
3. "Does the County consider the publication of 3D building masses or geometry derived from
   (extruded/transformed from) this footprint dataset, as part of a commercial software product,
   to be within the scope of permitted use, or does it require separate written permission?"
4. "Is there a specific attribution format the County requires for commercial or public-facing
   products that incorporate this dataset or geometry derived from it?"
5. "Does the County impose, or are downstream users subject to, any Esri ArcGIS Online
   platform-level restriction on bulk/automated extraction of this FeatureServer's data and its
   storage/processing on third-party cloud infrastructure, separate from the County's own stated
   terms?"

---

## Source Register

All sources accessed/re-verified directly in this research session on 2026-06-30.

| # | Source | Authority | URL | Finding |
|---|---|---|---|---|
| S1 | ArcGIS Item JSON | Miami-Dade County (MDPublisher) | `arcgis.com/sharing/rest/content/items/d511e9ebc5aa4f49a23ff5fa2fb99786?f=json` | Owner, license text, lineage, contact |
| S2 | BuildingFootprint2D_gdb FeatureServer JSON | Miami-Dade County (MDPublisher) | `services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer?f=json` | Empty `copyrightText`; `Query,Extract` capabilities; CRS |
| S3 | ArcGIS Hub v3 dataset API | ArcGIS / Miami-Dade County | `hub.arcgis.com/api/v3/datasets/d511e9ebc5aa4f49a23ff5fa2fb99786_0` | License text cross-check; attribution credit |
| S4 | Open Data Hub dataset page (alt domain) | Miami-Dade County | `opendata.miamidade.gov/datasets/MDC::building-footprint-2d/about` | Confirms same item on second portal alias; full content not renderable |
| S5 | Open Data Policy page (both domains) | Miami-Dade County | `gis-mdc.opendata.arcgis.com/pages/open-data-policy`, `opendata.miamidade.gov/pages/open-data-policy` | Page exists; body content NOT retrievable (JS-rendered) — attempted via direct fetch, Wayback Machine (blocked), search cache |
| S6 | Florida Statute § 119.01 | Florida Legislature | `leg.state.fl.us/Statutes/.../0119/Sections/0119.01.html` | Public-records copying right; copyright/trade-secret carve-out |
| S7 | Florida AG Opinion 2003-42 | Florida Attorney General | `myfloridalegal.com/ag-opinions/records-license-agreements-for-county-maps` | County cannot license-restrict GIS redistribution; flags independent federal-copyright exposure for contractor-sourced material |
| S8 | ArcGIS Online Terms of Use (doc) | Esri | `doc.arcgis.com/en/arcgis-online/reference/terms-of-use.htm` | Content owner's stated terms govern public items |
| S9 | ArcGIS Online Access and Use Constraints (doc) | Esri | `doc.arcgis.com/en/arcgis-online/reference/access-use-constraints.htm` | Default-permissive only when no terms are stated; not applicable here since terms exist |
| S10 | Miami-Dade GIS Data Service page | Miami-Dade County | `miamidade.gov/global/service.page?Mduid_service=ser1468850841882434` | Free-download statement; general contact info |
| Cross-ref | Sibling independent audit (same day, different branch) | GlytchDraft repository | `docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md` | Independently reached the same dataset identity and `LICENSE NOT CONFIRMED` disposition |

**Esri Master Agreement (E204/E204CW family)**: attempted (`esri.com/en-us/legal/terms/full-master-agreement`)
but only an index of linked PDFs was retrievable; the only available summary of its substantive
terms could not be independently verified against primary text and is **not** included in the
Source Register as a relied-upon source. See Section 9.

---

## Final License Disposition

```
FOOTPRINT LICENSE: NOT CONFIRMED
```

The evidence is directionally favorable (no stated prohibition on commercial use, redistribution,
or derivative works; Florida law constrains the county's own ability to impose license
restrictions) but conclusive confirmation requires resolving the contractor-rights question
(Section 6), obtaining the Open Data Policy text (Section 2/13), and ideally written agency
confirmation of the specific GlitchOS commercial 3D-derivative use case (Section 15).
`production_allowed` and `footprint_source.license` must remain unchanged pending that
confirmation.

---

## Compliance Confirmations

- `production_allowed` was not changed; not modified by this research.
- `REAL_DATA_EXECUTION_ENABLED` was not changed; not modified by this research.
- No real Miami data was downloaded, processed, or uploaded during this research.
- No `/mnt/t7` writes occurred.
- No implementation or pipeline code was changed.
- This document is research/documentation only.
