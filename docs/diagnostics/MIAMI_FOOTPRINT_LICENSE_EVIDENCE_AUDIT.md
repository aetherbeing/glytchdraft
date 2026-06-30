# Miami Footprint License Evidence Audit

**Branch:** `research/miami-footprint-license`
**Base commit:** `6a5dabb9a0f82121b307cfb18ac04b390d3f8415`
**Audit date:** 2026-06-30
**Auditor:** Claude Sonnet 4.6 (Instance 2 — independent research instance)
**Instance role:** Footprint-license evidence and provenance research only.
**Scope constraint:** Documentation and provenance research only. No code changes. No config
changes. No modification of `production_allowed`, `REAL_DATA_EXECUTION_ENABLED`, or any
pipeline authorization flag.

---

## 1. Executive Conclusion

The Miami-Dade County Building Footprint 2D dataset is published openly and is freely
downloadable with no stated use restrictions beyond an accuracy disclaimer. Florida law
(Chapter 119, Florida Statutes) and Florida Attorney General Opinion 2003-42 together
strongly indicate that Miami-Dade County cannot assert copyright over its GIS maps or impose
license restrictions on their redistribution, including for commercial purposes.

However, **full license confirmation is not possible from external evidence alone** because:

1. The dataset was produced in part by private contractors (GPI, Woolpert, ESRI). Whether
   Miami-Dade County obtained unrestricted title or work-for-hire status from those
   contractors is not established in any publicly available document.
2. The ArcGIS Hub portal contains an "Open Data Policy" page whose full text could not be
   retrieved during this audit (JavaScript-rendered; content not accessible to automated
   inspection).
3. No explicit affirmative license granting commercial use, redistribution, or 3D derivative
   work is attached to the dataset — only an accuracy disclaimer.
4. Attribution requirements, if any, are not prescribed in writing.

**Final license disposition: LICENSE NOT CONFIRMED**

The evidence does not indicate incompatibility. The predominant legal picture suggests
usability. But the production gate must remain closed until the unresolved contractor
copyright question is resolved, the Open Data Policy page content is obtained, and — ideally —
written confirmation is obtained from gis@miamidade.gov.

---

## 2. Scope and Proposed GlitchOS Use

The proposed GlitchOS use of the Miami-Dade County Building Footprint 2D data is:

| Dimension | Description |
|-----------|-------------|
| Use type | Commercial interactive 3D city viewer |
| Product form | Extruded building masses derived from footprint geometry + LiDAR heights |
| Target audience | General public (web viewer) |
| Revenue model | Commercial (Phase 2+ economy, subscriptions, or similar) |
| Spatial coverage | Miami-Dade County geographic extent |
| Derived outputs | GLB tiles, building metadata JSON, audit manifests, tile manifests |
| Publication | Public viewer endpoint; potential API responses |
| Redistribution | Derived 3D assets (not raw source data) distributed to end users |

The analysis in this report applies to this specific proposed use. A more restricted use
(internal analysis only, no publication) would have a more favorable legal profile.

---

## 3. Configured Repository Source

Sources reviewed: `configs/cities/miami.json`, `configs/miami.status.json`,
`docs/DATA_PROVENANCE.md`, `docs/DATA_INVENTORY.md`, `scripts/hero_tile/01_clip_footprints.py`,
`HANDOFF.md`, `AUDIT_FINDINGS.md`.

### 3.1 Configured dataset identity

| Field | Value |
|-------|-------|
| Dataset name (configured) | "Miami Building Footprints" |
| Source file (local) | `Building_Footprint_2D_2018.geojson` (GeoJSON) |
| Shapefile path (original) | `C:\Users\Glytc\OneDrive\Desktop\GLYTCHDRAFT_MIAMI\Building_Footprint_2D_2018\Building_Footprint_2D_2018.shp` |
| Publisher (configured) | "Miami-Dade County GIS" |
| Portal (configured) | gis-mdc.opendata.arcgis.com |
| Source URL (configured) | Not recorded beyond portal domain |
| Layer number | Not recorded |
| Download date | Not recorded |
| Feature count at use | 771,441 |
| Source CRS (configured) | OGC:CRS84 (GeoJSON) / EPSG:3857 in hero-tile clip script |
| UNIQUEID format | `D1_MDC_Building_*`, `D3_MDC_Building_*` |
| SOURCE field values | P=photogrammetry, L=LiDAR, null=unknown |
| License field | `open_data_terms_unconfirmed` |
| Production allowed | `false` |
| Notes | "Manually verify at gis-mdc.opendata.arcgis.com before setting production_allowed=true" |

### 3.2 Local files and provenance

`DATA_INVENTORY.md` records the dataset as `MIA-BF-001` with status `untouched`, noting 771,441
features county-wide and listing attributes: `UNIQUEID`, `SOURCE`, `YEARUPDATE`, `TYPE`,
`HEIGHT` (often null), `Shape__Area`, `Shape__Length`.

`docs/FIRST_OPEN_CHECKLIST.md` shows the workflow assumed downloading
`Building_Footprint_2D_2018.geojson` directly from the portal.

`scripts/hero_tile/01_clip_footprints.py` reads the shapefile from the local Windows path
shown above. No automated download script for the footprint dataset was found in the
repository. The source URL and download date are not recorded in any repository file.

---

## 4. Authoritative Dataset Identity

Research performed: ArcGIS REST API item metadata, ArcGIS Hub search, ArcGIS FeatureServer
inspection, web searches, Florida legal research.

### 4.1 Primary identification

| Field | Value |
|-------|-------|
| Exact dataset title | **Building Footprint 2D** |
| Publishing agency | Miami-Dade County Information Technology Department (ITD) |
| Data owner | Miami-Dade County |
| Organizational unit | Geospatial Infrastructure Support Group |
| ArcGIS organization ID | 8Pc9XBTAsYuxx9Ny |
| ArcGIS Item ID | **d511e9ebc5aa4f49a23ff5fa2fb99786** |
| ArcGIS Item status | `public_authoritative` |
| Dataset page | https://gis-mdc.opendata.arcgis.com/datasets/MDC::building-footprint-2d/about |
| Canonical alternate URL | https://gis-mdc.opendata.arcgis.com/datasets/d511e9ebc5aa4f49a23ff5fa2fb99786_0 |
| ArcGIS Item JSON | https://www.arcgis.com/sharing/rest/content/items/d511e9ebc5aa4f49a23ff5fa2fb99786?f=json |
| FeatureServer | https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer |
| Layer ID | 0 |
| Layer name | BuildingFootprint2D |
| Layer type | Polygon Feature Layer |
| Published | June 14, 2018 (Unix: 1528995787000) |
| Last modified | December 29, 2024 (Unix: 1767121026000) |
| Current feature count | 863,196 |
| Geographic coverage | Miami-Dade County, Florida (~938–969 sq mi) |
| Spatial reference (service) | EPSG:3857 (WKT: WGS_1984_Web_Mercator_Auxiliary_Sphere; WKID 102100) |
| Data format | Feature Service; download exports: GeoJSON, Shapefile, GeoPackage, KML, CSV |
| Export capabilities | Query, Extract |
| Portal hub | Miami-Dade County Open Data Hub (gis-mdc.opendata.arcgis.com) |
| Contact | gis@miamidade.gov |
| Download fee | None — free public download |
| Owner (ArcGIS) | MDPublisher |

### 4.2 Jurisdictional identity

VERIFIED FACT:
The dataset belongs to Miami-Dade County government (a Florida county), not the City of Miami,
not a regional or state agency, not a federal agency, and not a third-party data provider.
The ArcGIS organization owner (`MDPublisher`, org `8Pc9XBTAsYuxx9Ny`) is Miami-Dade County's
official ArcGIS Online publisher account. The item status is `public_authoritative`.

### 4.3 Data lineage

The ArcGIS Item metadata states:

> "Data derives from 2018 GPI LiDAR with 2021 Woolpert updates."
> "ESRI contracted to provide planimetric updates for ~969 square miles within and outside the
> UDB, updated in 2021."

Three private contractors are identified in the data lineage:
- **GPI** (Geospatial Products and Information) — 2018 LiDAR data collection and
  planimetric feature extraction
- **Woolpert** — 2021 planimetric update
- **ESRI** — planimetric update execution contractor (contract number BW8207-2/12 cited in
  metadata)

The dataset the project downloaded (771,441 features) corresponds to the 2018-era version of
the dataset. The current version (863,196 features, last modified December 29, 2024) includes
subsequent updates.

---

## 5. Source and Provenance Reconciliation

### 5.1 Reconciliation table

| Dimension | Repository (Configured) | Authoritative (Verified) | Match? |
|-----------|------------------------|--------------------------|--------|
| Dataset title | "Miami Building Footprints" | "Building Footprint 2D" | PARTIAL — official title differs |
| Publisher | "Miami-Dade County GIS" | Miami-Dade County ITD, Geospatial Infrastructure Support Group | MATCH (same agency) |
| ArcGIS Item ID | Not recorded | d511e9ebc5aa4f49a23ff5fa2fb99786 | GAP — not documented |
| Service URL | Not recorded | https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/.../BuildingFootprint2D_gdb/FeatureServer | GAP — not documented |
| Layer ID | Not recorded | Layer 0 | GAP — not documented |
| Download portal | gis-mdc.opendata.arcgis.com | gis-mdc.opendata.arcgis.com | MATCH |
| Feature count | 771,441 | 863,196 (current) | MISMATCH — dataset updated since download |
| Dataset source CRS | OGC:CRS84 / EPSG:3857 | EPSG:3857 service; CRS84 in GeoJSON download | MATCH (GeoJSON downloads as CRS84) |
| Download date | Not recorded | Unknown | GAP — not documented |
| Local filename | `Building_Footprint_2D_2018.geojson` | Official title does not include "2018" | INCONSISTENCY — year in local name not in official title |
| UNIQUEID format | `D3_MDC_Building_12375` | Matches UNIQUEID field (String, 50 chars) | MATCH |
| SOURCE field | P/L/null | SOURCE field in layer metadata | MATCH |
| License (configured) | open_data_terms_unconfirmed | Custom / accuracy disclaimer only | MATCH (unconfirmed is correct) |
| Attribution | Not recorded | "Miami-Dade County ITD - Geospatial Infrastructure Support Group" | GAP — not documented |
| Legal terms | Not researched | Accuracy disclaimer only; Florida law controls | GAP — was not previously researched |

### 5.2 Source identity conclusion

VERIFIED FACT:
The repository's configured source (`Building_Footprint_2D_2018.geojson`) is the Miami-Dade
County "Building Footprint 2D" dataset (ArcGIS Item ID d511e9ebc5aa4f49a23ff5fa2fb99786),
downloaded from gis-mdc.opendata.arcgis.com. The UNIQUEID format (`D3_MDC_Building_*`),
publisher, feature attributes, and portal all match. The "2018" in the local filename refers
to the 2018 GPI LiDAR vintage from which the dataset was derived, not a separate official
name.

VERIFIED FACT:
The feature count at the time of project download (771,441) is lower than the current
authoritative count (863,196). The dataset has received at least one update since the project
downloaded it. The exact downloaded version (commit/snapshot) is not recorded in the
repository.

---

## 6. Governing Legal Documents

### 6.1 Dataset-level license (ArcGIS Item API, retrieved 2026-06-30)

Source: ArcGIS Item JSON, field `licenseInfo`, Item ID d511e9ebc5aa4f49a23ff5fa2fb99786.

Verbatim text:

> "Miami-Dade County provides this data for use 'as is'. The areas depicted by this
> map/data are approximate, and are not accurate to surveying or engineering standards.
> The maps/data shown here are for illustration purposes only and are not suitable for
> site-specific decision making. Information found here should not be used for making
> financial or any other commitments. Miami-Dade County provides this information with the
> understanding that it is not guaranteed to be accurate, correct or complete and conclusions
> drawn from such information are the sole responsibility of the user. While every effort has
> been made to ensure the accuracy, correctness and timeliness of materials presented,
> Miami-Dade County assumes no responsibility for errors or omissions, even if Miami-Dade
> County is advised of the possibility of such damage."

VERIFIED FACT:
This text is a warranty and accuracy disclaimer. It:
- Does not grant a named license (not Creative Commons, not public domain designation)
- Does not explicitly permit or restrict commercial use
- Does not explicitly permit or restrict redistribution
- Does not explicitly permit or restrict derivative works
- Does not impose an attribution requirement
- Does disclaim accuracy, fitness for purpose, and county liability

The ArcGIS Hub dataset page designates license type as "Custom." No Creative Commons badge or
other standard license badge is applied.

### 6.2 ArcGIS FeatureServer copyright field

Source: FeatureServer JSON, field `copyrightText`, retrieved 2026-06-30.

Value: `""` (empty string)

VERIFIED FACT:
The FeatureServer exposes no copyright text. No legal notice is embedded in the service
response.

### 6.3 Florida Statute § 119.01 — Public Records Policy

Source: Florida Legislature, https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&URL=0100-0199/0119/Sections/0119.01.html, retrieved 2026-06-30.

Key provisions:
- "All state, county, and municipal records are open for personal inspection and copying by
  any person."
- "Providing access to public records is a duty of each agency."
- Access is "[s]ubject to the restrictions of copyright and trade secret laws and public
  records exemptions."

VERIFIED FACT:
Miami-Dade County building footprint data, as a county government record, is subject to
Florida's public records law. This establishes a duty to provide access. However, access
rights do not automatically resolve copyright ownership, particularly for contractor-produced
components.

### 6.4 Florida Attorney General Opinion 2003-42 (AGO 2003-42)

Source: Florida AG, September 2, 2003.
URL: https://www.myfloridalegal.com/ag-opinions/records-license-agreements-for-county-maps
Retrieved: 2026-06-30.

Issue addressed: Whether a Florida county (Palm Beach County) could require license agreements
for its GIS maps and related data to regulate redistribution for commercial purposes.

Conclusion (verbatim):
> "In the absence of a statute authorizing the county to restrict the use of these public
> records by requiring license agreements for its Geographic Information Systems maps and
> related data, the county does not possess such authority."
> "Palm Beach County is not authorized to obtain copyright protection and require license
> agreements for its Geographic Information Systems (GIS) maps and related data in order to
> regulate and authorize redistribution of these materials for commercial use."

Key reasoning:
- Florida's Public Records Law mandates disclosure
- Counties cannot claim copyright over public records without explicit legislative authorization
- Section 119.084 (copyright of agency data processing software) applies only to software, not
  geographic data
- Counties may charge duplication fees but cannot impose license restrictions

REASONABLE INTERPRETATION:
AGO 2003-42 applies to Palm Beach County but is persuasive authority for all Florida counties,
including Miami-Dade County. It establishes that Florida county GIS data cannot be restricted
from redistribution for commercial purposes through licensing requirements. However, this is an
AG opinion, not a court ruling, and does not have the force of law.

UNRESOLVED QUESTION:
AGO 2003-42 primarily addresses what the county can do (restrict). It does not directly
address whether third-party contractor copyright claims would survive Florida's public records
framework. The Florida Statute §119.01 specifically notes that access is subject to "the
restrictions of copyright and trade secret laws."

### 6.5 Florida Constitution and case law (Microdecisions, Inc. v. Skinner)

Source: Wikipedia, "Copyright status of works by the government of Florida," retrieved
2026-06-30.

Under Florida law:
- Florida state and county governments are not permitted to claim copyright on their public
  records unless the legislature specifically authorizes it
- The legislature has authorized copyright only for narrowly defined categories: Department of
  the Lottery, Department of Citrus, and university research departments
- GIS data and maps produced by county governments are not in any authorized copyright
  category
- The *Microdecisions* case held that a copyright defense would carve out an exemption to
  the open records law and requires specific legislative authorization

REASONABLE INTERPRETATION:
Miami-Dade County itself cannot assert copyright in the Building Footprint 2D dataset.
The County's disclaimer language ("for use 'as is'") is a liability disclaimer, not a
copyright assertion.

### 6.6 Open Data Policy page (not retrieved)

A page at https://gis-mdc.opendata.arcgis.com/pages/open-data-policy was identified through
web search and confirmed to exist. The page title is "Open Data Policy — Hub Page."

UNRESOLVED QUESTION:
The content of this page could not be retrieved during this audit because the ArcGIS Hub portal
uses JavaScript rendering not accessible to this research tool. The full text of the
Miami-Dade County Open Data Policy is unknown. It may contain additional permissions, license
grants, or restrictions that would affect the analysis.

### 6.7 No portal-wide terms of use found

No Miami-Dade County portal-wide terms of service governing the GIS Open Data Hub were
identified in accessible (non-JavaScript-rendered) form during this audit. The county's
general website (miamidade.gov) references a "Disclaimer" and "Privacy Statement" in its
footer, but the full text of these documents was not accessible.

---

## 7. Access and Copying Rights

### 7.1 Is downloading the source permitted?

VERIFIED FACT:
The dataset is publicly accessible at gis-mdc.opendata.arcgis.com with no login required.
The ArcGIS FeatureServer declares capabilities "Query,Extract." The county's GIS Data Service
page states: "Most publicly available production data can be downloaded for free from the
Miami-Dade County Open Data Hub." Under Florida §119.01, public records must be available for
personal inspection and copying.

**Conclusion: Downloading is permitted.**

### 7.2 Is local storage permitted?

VERIFIED FACT:
No prohibition on local storage appears in any accessible legal document. Florida law mandates
the right to copy public records. No contractual restriction on storage has been identified.

**Conclusion: Local storage is permitted.**

### 7.3 Is copying into internal processing systems permitted?

REASONABLE INTERPRETATION:
No restriction on use in internal processing systems appears in any identified document. The
accuracy disclaimer does not restrict processing. Florida law supports the right to copy and
use public records.

**Conclusion: Internal processing is reasonably interpreted as permitted.**

### 7.4 Are automated downloads or API calls permitted?

REASONABLE INTERPRETATION:
The FeatureServer is a public ArcGIS REST API endpoint accessible without authentication. No
rate limits or API-specific terms of use were identified in accessible sources. Standard
ArcGIS platform terms apply to the ArcGIS Online infrastructure, but the Miami-Dade County
data itself has no identified prohibition on API access.

UNRESOLVED QUESTION:
ArcGIS Online's platform-level terms of service (ESRI/ArcGIS) were not reviewed. If the
FeatureServer is hosted on ArcGIS Online (organization 8Pc9XBTAsYuxx9Ny), ESRI's platform
terms may impose service-level restrictions on API access rates or commercial use of data
accessed via the platform. This is a secondary, platform-level risk that does not affect the
copyright analysis of the data itself.

---

## 8. Modification Rights

### 8.1 May the source geometry be transformed?

REASONABLE INTERPRETATION:
No restriction on geometric transformation appears in the license text or any identified
applicable law. The accuracy disclaimer suggests data is approximate; transforming it does not
violate any stated term.

**Conclusion: Transformation is reasonably interpreted as permitted.**

### 8.2 May the geometry be simplified, clipped, tiled, extruded, or otherwise modified?

REASONABLE INTERPRETATION:
No restriction on these operations appears in any identified applicable document. The project
already clips (scripts/hero_tile/01_clip_footprints.py), reprojects, and extrudes building
footprints. No legal barrier to these operations has been identified.

**Conclusion: These modifications are reasonably interpreted as permitted.**

### 8.3 May the data be combined with LiDAR and other public datasets?

REASONABLE INTERPRETATION:
The accuracy disclaimer does not restrict combining the data with other sources. USGS 3DEP
LiDAR data is federal public domain (17 U.S.C. § 105). No restriction on combination with
public-domain data has been identified.

**Conclusion: Combination with USGS 3DEP LiDAR is reasonably interpreted as permitted.**

### 8.4 Are derivative databases permitted?

UNRESOLVED QUESTION:
The question of whether a derivative database (e.g., `miami_footprints_4326.geojson` derived
from the county source) may be internally held and processed is not explicitly addressed.
Florida law and AGO 2003-42 support unrestricted internal use. Whether derivative databases
may be *redistributed* is a separate question (see Section 11).

---

## 9. Commercial-Use Rights

### 9.1 Is commercial use explicitly permitted?

VERIFIED FACT:
No language in the dataset's license text or any identified Miami-Dade County policy
explicitly grants commercial use. The license text is a disclaimer only. No "CC BY" or
equivalent commercial-use grant has been identified.

**Answer: Commercial use is NOT explicitly permitted in any identified document.**

### 9.2 Is commercial use silent but reasonably implied?

REASONABLE INTERPRETATION:
Florida AGO 2003-42 concluded that a county cannot restrict redistribution of GIS maps for
commercial use. If the county lacks authority to prohibit commercial use under Florida law,
the silence on commercial use in the license text is consistent with commercial use being
unrestricted.

Florida courts have held that the purpose of a public records request is immaterial, and
commercial use cannot be discriminated against under Florida's public records law.

**Answer: Commercial use is reasonably (though not conclusively) implied as unrestricted
under Florida law.**

### 9.3 Is commercial use restricted?

VERIFIED FACT:
No explicit commercial use restriction appears in any identified document associated with this
dataset.

**Answer: No identified commercial use restriction.**

### 9.4 Is agency permission required?

REASONABLE INTERPRETATION:
Under AGO 2003-42, a Florida county cannot require license agreements for commercial
redistribution of GIS maps. Therefore the county cannot require permission for commercial
use. However, the contractor copyright question (Section 6 above) creates uncertainty: if
GPI or Woolpert hold unassigned copyright, their permission could theoretically be required.

**Answer: County permission is not required under Florida law, but the contractor copyright
question creates an unresolved pathway through which permission could theoretically be needed
from third-party contractors.**

### 9.5 Does the project's proposed use exceed ordinary public-information use?

REASONABLE INTERPRETATION:
Publishing a commercial 3D city viewer is a substantially more expansive use than public-
information inspection or personal copying. Whereas Florida law clearly permits copying and
personal use, the proposed GlitchOS use involves:
- Commercial revenue generation
- Public redistribution of derived 3D assets to end users
- Rendered visual representations associated with the footprint data

This is a use case not directly addressed by any identified document. It is a reasonable
extension of permitted use under Florida law but goes beyond the paradigmatic case of
"personal inspection and copying."

---

## 10. Derivative-Output Rights

### 10.1 Permissibility by output type

| Output type | Analysis | Conclusion |
|-------------|----------|------------|
| Extruded 3D building masses | Derived from footprint geometry + LiDAR; LiDAR is public domain | UNRESOLVED QUESTION — depends on contractor copyright resolution |
| Calculated building heights | Derived primarily from public-domain LiDAR; footprints used for spatial joining | REASONABLE INTERPRETATION: Permitted (height is a measured attribute, not a footprint) |
| Roof characteristics | Derived from LiDAR; footprint used as spatial context only | REASONABLE INTERPRETATION: Permitted |
| Footprint area (calculated) | Mathematical attribute of the footprint geometry | UNRESOLVED QUESTION — a calculation on copyrighted geometry |
| Facade estimates | Derived from height × perimeter; geometry-dependent | UNRESOLVED QUESTION |
| Building metadata | Derived from UNIQUEID, SOURCE, YEARUPDATE attributes | REASONABLE INTERPRETATION: Permitted under Florida public records law |
| Tile manifests | Structural metadata, no raw geometry | REASONABLE INTERPRETATION: Permitted |
| Rendered imagery | Visual rendering of derived 3D assets | UNRESOLVED QUESTION — rendering is a derivative work |
| Interactive 3D viewers | Contains derived geometry from footprints | UNRESOLVED QUESTION |
| AR/VR visualizations | Contains derived geometry | UNRESOLVED QUESTION |
| API responses with derived attributes | Depends on attribute type | PARTIAL — permitted for measured data, unresolved for geometric derivatives |

### 10.2 The key distinction for this project

The most critical distinction is:
- **Publishing public records data** (access rights clearly established by Florida law)
- **Publishing modified source geometry** (reasonably interpreted as permitted; no identified
  restriction)
- **Publishing derived 3D assets built on the geometry** (unresolved — no identified grant;
  not addressed by AGO 2003-42)

The proposed GlitchOS product publishes the third category: 3D building masses whose geometry
derives from county footprints. Whether this falls within the scope of Florida's public records
rights or requires a separate permission is an unresolved legal question.

---

## 11. Redistribution Rights

### 11.1 Original downloaded footprint dataset

REASONABLE INTERPRETATION:
Under AGO 2003-42, Miami-Dade County cannot restrict redistribution of its GIS maps for
commercial purposes. Therefore redistributing the original downloaded dataset appears to be
permitted.

UNRESOLVED QUESTION:
If GPI or Woolpert hold unassigned copyright in any component of the dataset, redistribution
without their consent could create infringement liability. This risk is not eliminated by
Florida law.

### 11.2 Filtered subsets, tiled footprints, GeoJSON exports

REASONABLE INTERPRETATION:
Filtered subsets and format-converted exports (e.g., the project's `miami_footprints_4326.geojson`)
are reasonably interpreted as permitted under the same reasoning as the original.

### 11.3 Transformed footprints

REASONABLE INTERPRETATION:
Reprojected or clipped subsets (e.g., EPSG:32617 versions) are reasonably interpreted as
permitted. Coordinate transformation is a technical operation, not substantively different
from the original data.

### 11.4 Generated 3D assets (GLB tiles, derived building masses)

UNRESOLVED QUESTION:
GLB tiles containing building masses derived from county footprints are the farthest downstream
derivative in this project. The legal characterization of these assets is not addressed by any
identified document. They may be treated as:
(a) An expression of public-domain information (in which case redistribution is unrestricted), or
(b) A derivative work based on potentially copyrighted contractor data (in which case permission
    from the contractor may be required).

No authoritative resolution of this question was identified during this audit.

### 11.5 Screenshots or rendered scenes

UNRESOLVED QUESTION:
Same analysis as 3D assets. Rendered imagery derived from footprint-based masses is a visual
derivative. Not addressed in any identified document.

---

## 12. Attribution Requirements

VERIFIED FACT:
No specific attribution text or attribution requirement is stated in the dataset's license
text (which is an accuracy disclaimer only). The FeatureServer `copyrightText` field is empty.

The ArcGIS Item `accessInformation` field states:
> "Miami-Dade County ITD - Geospatial Infrastructure Support Group"

This field is a credit/attribution field in ArcGIS, but it does not impose a contractual
attribution obligation.

The OSM import project used the following changeset tag as attribution:
> `source=Miami-Dade County GIS Open Data, http://gis.mdc.opendata.arcgis.com`

RECOMMENDED DECISION:
Absent a formal attribution requirement, GlitchOS should nonetheless attribute the data source
to avoid false attribution claims and as good practice. Recommended attribution text:

> Building footprint data: Miami-Dade County ITD — Geospatial Infrastructure Support Group,
> available at https://gis-mdc.opendata.arcgis.com. Provided for use "as is" without accuracy
> guarantees.

This attribution should appear in:
- Repository documentation (DATA_PROVENANCE.md)
- Asset manifests
- Viewer credits (if footprint data is attributed in the viewer)
- Legal notices file

Where attribution must appear in any public-facing commercial product remains unresolved
pending confirmation of the governing terms.

---

## 13. Disclaimer Requirements

The dataset's license text establishes several disclaimers that, while not contractually
mandated for downstream users, are prudent to carry forward in derivative products.

### 13.1 Accuracy

RECOMMENDED DECISION:
Any public-facing viewer or product derived from this dataset should carry an accuracy
disclaimer consistent with the source: building footprints are approximate and not accurate
to surveying or engineering standards.

### 13.2 Not suitable for site-specific decisions

RECOMMENDED DECISION:
The source explicitly states data is "not suitable for site-specific decision making." This
caveat should be surfaced in any product legal notices, particularly for any viewer feature
that could be used for navigation, emergency response, or property decisions.

### 13.3 No financial commitments

The source states information "should not be used for making financial or any other
commitments." GlitchOS products involving building values, commercial transactions, or
financial data derived from or associated with these footprints should carry this disclaimer.

### 13.4 County not endorsing

Implied from "provided by Miami-Dade County for use 'as is'": Miami-Dade County does not
endorse or certify any GlitchOS product derived from this data.

### 13.5 Building condition, current status, official-record status

The footprint data (last updated 2021 in the version the project uses) does not represent
current building stock. Buildings may have been demolished, constructed, or modified since
the data vintage. The data is not an official property record for legal or regulatory purposes.

---

## 14. Repository Gaps

The following gaps in the repository's documentation of the footprint source were identified:

| Gap | Severity | Detail |
|-----|----------|--------|
| Download date not recorded | HIGH | No date recorded anywhere in the repository. The exact snapshot of the dataset cannot be identified or verified without a download timestamp. |
| ArcGIS Item ID not recorded | HIGH | The definitive identifier for the dataset (d511e9ebc5aa4f49a23ff5fa2fb99786) is not documented anywhere in the repository. |
| FeatureServer URL not recorded | HIGH | The authoritative service endpoint is not recorded in any config or provenance file. The portal URL is noted but not the item or service URL. |
| Download source URL not recorded | HIGH | Only the portal domain (gis-mdc.opendata.arcgis.com) is noted; no specific download URL, feature layer URL, or item page URL is recorded. |
| Attribution text not recorded | MEDIUM | The `accessInformation` value from the ArcGIS item is not captured anywhere. |
| Contractor lineage not documented | MEDIUM | GPI (2018), Woolpert (2021), and ESRI (planimetric updates) are not mentioned in any repository provenance document. |
| Dataset feature count at download vs. current | MEDIUM | The dataset has been updated (863,196 vs. 771,441 features). The download version is not pinned. |
| Open Data Policy terms unknown | HIGH | The Miami-Dade County Open Data Policy page (gis-mdc.opendata.arcgis.com/pages/open-data-policy) was not inspected and its content is unknown. |
| No source hash recorded | HIGH | No SHA-256 or other hash of the downloaded footprint file is recorded. Provenance cannot be independently verified. |
| Local shapefile path uses OneDrive | MEDIUM | `scripts/hero_tile/01_clip_footprints.py` hardcodes `C:\Users\Glytc\OneDrive\Desktop\GLYTCHDRAFT_MIAMI\...`. This path is not in any canonical data location and may not match the file used in production pipeline runs. |
| License label "open_data_terms_unconfirmed" | LOW | Correctly captures uncertainty; no action needed until confirmed. |

---

## 15. Unresolved Questions

The following questions must be resolved before the production gate can open:

### Q1. Contractor copyright (CRITICAL)

The Building Footprint 2D dataset derives from work product of GPI (2018), Woolpert (2021),
and ESRI (planimetric updates, contract BW8207-2/12). Under U.S. copyright law, works produced
by independent contractors are not automatically "works for hire" — copyright remains with the
contractor absent a written assignment or work-for-hire agreement.

**Question:** Did Miami-Dade County obtain a full rights assignment or work-for-hire
acknowledgment from GPI, Woolpert, and ESRI covering the produced planimetric data? If so,
do those rights extend to public redistribution and commercial use by downstream users?

**How to resolve:** Contact gis@miamidade.gov or Miami-Dade County ITD legal counsel.
Request copies of data rights provisions in the relevant contracts or a written statement
confirming the data is freely usable for commercial redistribution and derivative works.

### Q2. Open Data Policy content (HIGH)

The Miami-Dade County Open Data Hub has a dedicated Open Data Policy page at
https://gis-mdc.opendata.arcgis.com/pages/open-data-policy. This page's content was not
retrievable during this audit.

**Question:** Does the Open Data Policy grant explicit rights for commercial use, redistribution,
and derivative works? Does it impose attribution requirements or other conditions?

**How to resolve:** Visit the page directly in a browser. Download or screenshot the full text.
Add the contents to this report or to a supplementary file.

### Q3. Applicability of AGO 2003-42 to Miami-Dade County (MEDIUM)

AGO 2003-42 was issued in response to a question from Palm Beach County. Its conclusion
applies specifically to that county under Florida law, but is persuasive (not binding)
authority for Miami-Dade County.

**Question:** Has Miami-Dade County ever challenged, departed from, or narrowed the application
of AGO 2003-42 with respect to its own GIS data?

**How to resolve:** Review any Miami-Dade County ordinances or resolutions regarding GIS data
licensing. Contact the county attorney's office.

### Q4. "Illustration purposes only" as a use restriction (LOW)

The license text states the data is "for illustration purposes only and not suitable for
site-specific decision making." This language appears in an accuracy disclaimer context, not
a use restriction context.

**Question:** Could this language be interpreted to restrict use in a commercial 3D visualization
product where buildings are depicted in a game-like or entertainment context?

**Analysis:** This language is a standard accuracy disclaimer used by government GIS portals
and is not a contractual use restriction. Courts interpreting similar government disclaimers
have consistently found them to be liability-limitation language, not use-restriction language.
Risk: LOW. But the question is not zero if a commercial product prominently uses the data in
ways inconsistent with "illustration."

### Q5. ESRI ArcGIS platform-level terms (LOW)

The FeatureServer is hosted on ArcGIS Online. ESRI's platform terms of service govern access
to its infrastructure. These terms may impose service-level conditions on automated access
(rate limits, bot access) even if the underlying data is freely usable.

**Question:** Do ESRI's ArcGIS Online terms restrict bulk download or commercial use of public
data accessed via FeatureServer endpoints?

**How to resolve:** Review ESRI's ArcGIS Online Terms of Use. This is a secondary risk that
applies to data access method, not to the data rights themselves.

### Q6. Attribution in a commercial product (LOW)

No formal attribution requirement was identified. However, publishing a commercial product
without crediting Miami-Dade County creates a potential false attribution or passing-off risk.

**Question:** What is the minimally sufficient attribution for a commercial product using
this data?

**How to resolve:** Adopt the recommended attribution from Section 12 as a conservative
minimum until formal policy confirmation is obtained.

---

## 16. Recommended Repository Changes

Do not implement these changes until the production gate is otherwise ready. These are
documentation corrections, not authorization approvals.

### R1. Record the ArcGIS Item ID in `configs/cities/miami.json`

Add `footprint_source_detail.arcgis_item_id = "d511e9ebc5aa4f49a23ff5fa2fb99786"`.

### R2. Record the service URL in `configs/cities/miami.json`

Add `footprint_source_detail.service_url = "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer"`.

### R3. Record the dataset page URL

Add `footprint_source_detail.dataset_page = "https://gis-mdc.opendata.arcgis.com/datasets/MDC::building-footprint-2d/about"`.

### R4. Record the attribution text

Add `footprint_source_detail.attribution = "Miami-Dade County ITD - Geospatial Infrastructure Support Group"`.

### R5. Record the download date and feature count snapshot

When the exact download date is known (or the next download is performed), record the date,
feature count, and a SHA-256 hash of the downloaded GeoJSON file.

### R6. Record contractor lineage

Add a provenance note identifying GPI (2018), Woolpert (2021), and ESRI (planimetric updates)
as data production contractors, noting that contractor rights assignment status is unresolved.

### R7. Update `docs/DATA_PROVENANCE.md`

Change the source URL from `https://gisweb.miamidade.gov/` to the authoritative portal
`https://gis-mdc.opendata.arcgis.com/datasets/MDC::building-footprint-2d/about`.

### R8. Add Open Data Policy content when retrieved

Once the Open Data Policy page at https://gis-mdc.opendata.arcgis.com/pages/open-data-policy
is retrieved, add a summary of its terms to this report or a separate supplementary document.

### R9. Record the governing disclaimer verbatim

The verbatim disclaimer text from Section 6.1 should appear in `docs/DATA_PROVENANCE.md`
alongside the dataset entry.

### R10. If license is confirmed

When the contractor copyright question and Open Data Policy content are resolved in favor of
commercial use, update:
- `configs/cities/miami.json`: `footprint_source_detail.license` → appropriate confirmed label
- `configs/miami.status.json`: `license_status` → `"confirmed"`
- `docs/DATA_PROVENANCE.md`: license status → `"confirmed"`
- `configs/cities/miami.json`: do NOT change `production_allowed` — that gate requires a
  separate pipeline review decision.

---

## 17. Recommended Production-Gate Decision

RECOMMENDED DECISION:
Keep `production_allowed = false`.

The production gate has two independent blockers:

**Blocker 1 (license):** The footprint license is not confirmed for commercial use,
redistribution, and 3D derivative works. The contractor copyright question (Q1) and the
Open Data Policy content (Q2) must be resolved before the license gate can be cleared.

**Blocker 2 (pipeline readiness):** Separate from license, the production gate has multiple
open pipeline issues (PM-1 through PM-8) that remain NO-GO per `MIAMI_TRUTH_RECONCILIATION.md`
and `MIAMI_PRODUCTION_GATE_EVIDENCE.md`. These are not addressed by this audit.

Clearing the license blocker alone is not sufficient to enable production. Both blockers
must be independently resolved.

### Minimum steps to clear the license gate

1. Retrieve and review the full text of the Miami-Dade County Open Data Policy page
   (https://gis-mdc.opendata.arcgis.com/pages/open-data-policy).
2. Contact gis@miamidade.gov and request:
   - Written confirmation that the Building Footprint 2D dataset is freely available for
     commercial use, including in commercial products that derive 3D building masses and
     publish them publicly.
   - Clarification of whether third-party contractor copyrights (GPI, Woolpert, ESRI) were
     assigned to the county and do not restrict downstream commercial use.
   - Confirmation of any required attribution language.
3. Record the response, date, and contact name in the repository.
4. Only then update the license field and license status.
5. If the county declines to confirm, or if the Open Data Policy imposes restrictions
   inconsistent with the proposed use, escalate to legal counsel.

---

## 18. Final License Disposition

```
LICENSE NOT CONFIRMED
```

**Reasoning:**

The evidence is relatively favorable. Florida law (§119 and AGO 2003-42) strongly suggests
Miami-Dade County cannot restrict GIS data redistribution for commercial purposes, and the
county's license text contains no explicit use restrictions. The data is publicly accessible,
freely downloadable, and the county has published it as `public_authoritative`.

However, "LICENSE CONFIRMED FOR PROPOSED USE" requires affirmative evidence supporting the
specific intended GlitchOS commercial use, including redistribution of 3D derivative assets
and commercial revenue generation. That evidence is not present because:

1. The contractor copyright question is unresolved. If GPI, Woolpert, or ESRI hold
   unassigned rights, the county's authority to grant unrestricted use is limited.
2. No explicit affirmative license has been applied to the dataset (not CC0, not CC BY,
   not a county-specific open-data license).
3. The Open Data Policy page content is unknown.

"LICENSE INCOMPATIBLE" is not warranted. No identified document prohibits the proposed use.
The legal picture points toward permissibility. The risk is procedural (no written confirmation)
rather than substantive (no prohibition).

---

## 19. Source Register

The following sources were reviewed during this audit. All sources accessed 2026-06-30.

| # | Source title | Authority | URL | Section | Finding | Confidence |
|---|-------------|-----------|-----|---------|---------|------------|
| S1 | Building Footprint 2D — ArcGIS Item JSON | Miami-Dade County (MDPublisher) | https://www.arcgis.com/sharing/rest/content/items/d511e9ebc5aa4f49a23ff5fa2fb99786?f=json | §6.1, §4 | License text (disclaimer only), item metadata, data lineage | HIGH |
| S2 | BuildingFootprint2D FeatureServer | Miami-Dade County (MDPublisher) | https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer?f=json | §4.1, §6.2 | Empty copyrightText; capabilities; field schema | HIGH |
| S3 | BuildingFootprint2D Layer 0 | Miami-Dade County (MDPublisher) | https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer/0?f=json | §4.1 | Field names and types confirmed (UNIQUEID, SOURCE, etc.) | HIGH |
| S4 | ArcGIS Hub Dataset Metadata API | ArcGIS / Miami-Dade County | https://hub.arcgis.com/api/v3/datasets/d511e9ebc5aa4f49a23ff5fa2fb99786_0 | §4.1, §6.1 | License type "Custom"; license text verbatim | HIGH |
| S5 | Florida Statute § 119.01 | Florida Legislature | https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&URL=0100-0199/0119/Sections/0119.01.html | §6.3 | Public records access policy; copyright exception noted | HIGH |
| S6 | Florida AG Opinion 2003-42 | Florida Attorney General | https://www.myfloridalegal.com/ag-opinions/records-license-agreements-for-county-maps | §6.4 | County cannot restrict GIS redistribution for commercial use | HIGH |
| S7 | Copyright status of works by the government of Florida | Wikipedia (secondary) | https://en.wikipedia.org/wiki/Copyright_status_of_works_by_the_government_of_Florida | §6.5 | Florida government works in public domain absent legislative authorization | MEDIUM (secondary source) |
| S8 | Miami-Dade GIS Open Data Hub | Miami-Dade County | https://gis-mdc.opendata.arcgis.com/ | §4 | Portal identification; dataset presence confirmed | HIGH |
| S9 | Miami-Dade GIS Data Service page | Miami-Dade County | https://www.miamidade.gov/global/service.page?Mduid_service=ser1468850841882434 | §6.6 | Free download statement; no usage restrictions stated | HIGH |
| S10 | Miami-Dade County Large Building Import — OSM Wiki | OpenStreetMap (secondary) | https://wiki.openstreetmap.org/wiki/Miami-Dade_County_Large_Building_Import | §6.4, §12 | "No license specified"; public domain claim under Florida §119; attribution tag format | MEDIUM (secondary, community interpretation) |
| S11 | Open Data Policy page | Miami-Dade County | https://gis-mdc.opendata.arcgis.com/pages/open-data-policy | §6.6 | Page exists; content NOT RETRIEVED | LOW (page identified but not read) |
| S12 | configs/cities/miami.json | GlytchDraft repository | /configs/cities/miami.json | §3 | Configured source, license field, production_allowed | HIGH |
| S13 | configs/miami.status.json | GlytchDraft repository | /configs/miami.status.json | §3 | license_status, production_allowed | HIGH |
| S14 | docs/DATA_PROVENANCE.md | GlytchDraft repository | /docs/DATA_PROVENANCE.md | §3 | Configured license "UNCONFIRMED — likely CC BY 4.0 but not verified" | HIGH |
| S15 | docs/DATA_INVENTORY.md | GlytchDraft repository | /docs/DATA_INVENTORY.md | §3 | Dataset MIA-BF-001 details | HIGH |
| S16 | scripts/hero_tile/01_clip_footprints.py | GlytchDraft repository | /scripts/hero_tile/01_clip_footprints.py | §3 | Source shapefile local path; 771,441 feature count reference | HIGH |
| S17 | HANDOFF.md | GlytchDraft repository | /HANDOFF.md | §3 | Production gate history; safety state | HIGH |
| S18 | AUDIT_FINDINGS.md | GlytchDraft repository | /AUDIT_FINDINGS.md | §3 | Footprint source references | HIGH |

---

## Compliance Confirmations

- `production_allowed` was NOT changed. It remains `false` in `configs/cities/miami.json` and `configs/miami.status.json`.
- `REAL_DATA_EXECUTION_ENABLED` was NOT changed. It remains `False`.
- No real Miami data was processed. No PDAL execution occurred.
- No writes to `/mnt/t7` occurred.
- No implementation code was changed.
- No pipeline authorization was changed.
- No controlled smoke authorization was issued.
- This report is documentation only.
