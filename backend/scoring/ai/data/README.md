# Administrative lookup snapshot

`admin_units.json` is a conservative snapshot for the 2025 reform, effective
1 July 2025. The source URLs are retained in the JSON. Each province references
the relevant paragraph of Resolution 202/2025/QH15; each ward references a
paragraph of Resolution 1685/NQ-UBTVQH15 (Ho Chi Minh City) or
1656/NQ-UBTVQH15 (Hanoi). Sources are published by the Government newspaper.

Coverage includes all 34 province names and their renamed 2025 predecessors,
plus **12 selected current wards**. The ward table is deliberately incomplete.
Add entries only after checking the official resolution. A named whole old unit
can map to its new ward only with matching old province and district. Partly
split units are recorded with `whole_unit: false` and never mapped from the old
name alone. Unsupported places, omitted districts on old names, and spelling
errors return `admin_unresolved`; they do not lower address completeness.

A current name also used by a partly split old ward remains unresolved without
an administrative version, even when the district is omitted. For example,
"Phường Cửa Nam, Hà Nội" could identify the old or new ward. A current name
shared only with a whole old ward that maps to the same place, such as Tân Định,
can resolve safely. Ambiguity does not imply that the buyer used a legacy name;
the legacy flag requires a distinct known old name or historical context.

Matching ignores Vietnamese diacritics, case, punctuation and administrative
prefixes (`P.`, `Q.`, `TP.`). HCM is an explicit abbreviation of Hồ Chí Minh.
Matching does not use fuzzy geographic guesses. Buyer text remains in
`normalized.raw`, and extracted spelling remains available in `parts`.

Completeness weights are fixed in code: house/building number 0.35, street/alley
line 0.25, written ward 0.25, written province 0.15. Missing or unresolved
administrative mappings do not change presence weights. For landmark-only
descriptions, street and house-number weights are excluded and completeness
is capped at 0.30. Districts carry no weight because the 2025 system has two
administrative levels. These are input features, never an order risk score.

The snapshot is not a live national registry. Later boundary changes need a
reviewed new table version. Gemini receives no mapping data and must return
administrative names as written, including old spellings.
