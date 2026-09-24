# Design Questions and Answers

This document records questions that come up when discussing the design
of VariantLens. It is meant as a reference for anyone reading the code,
including a future maintainer who wants to understand why certain
choices were made.

The questions are grouped into six sections: project overview,
architecture, data, evaluation, engineering practice, and general
research software questions.

---

## Section 1: Project overview

### 1.1 What problem does VariantLens solve?

Interpreting a rare Mendelian variant means checking ClinVar for
classification, gnomAD for allele frequency, and PubMed for supporting
literature. Done by hand, this takes between thirty and sixty minutes
per variant, and the PubMed search is often keyword-based, which misses
papers that use different terminology.

VariantLens automates the whole flow and produces a structured JSON
report in a few seconds.

### 1.2 Why a separate pipeline instead of using an existing tool?

Existing clinical tools such as Franklin and InterVar focus on ACMG
classification. VariantLens focuses on literature retrieval. The two
are complementary. There is also value in an open-source tool that
researchers can inspect and modify.

### 1.3 What is the current status?

MVP. Fifteen modules, seventy-four tests, CI on three Python versions,
Docker image, golden set of eight real variants, benchmark with three
retrieval strategies. Documented limitations. Phase 2 targets are
recorded in `docs/evaluation.md`.

### 1.4 Which parts of the scope are intentionally excluded?

Structural variants, somatic variants, clinical decision-making, and
variants of uncertain significance. The tool is not validated for
clinical use.

### 1.5 If you were to start over, what would you change?

Three things. Start with bulk data rather than the API. Use a larger
golden set from the beginning. Add the alias column to the variants
table before the first benchmark, not after.

---

## Section 2: Architecture

### 2.1 Why a modular architecture?

Three reasons. Separation of concerns: each module has one job.
Replaceability: swapping the retrieval strategy touches only one
module. Testability: modules with few dependencies can be mocked
independently.

### 2.2 How are modules organized?

Fifteen modules under `src/variant_lens/`:

- `parse`, `scope`, `fetch`, `annotate` — the annotation pipeline
- `retrieve`, `rank` — the retrieval pipeline
- `clinvar`, `clinvar_bulk`, `golden` — data layer for evaluation
- `report`, `cli` — output
- `schema`, `config`, `cache`, `warnings` — support

### 2.3 What is the dependency direction?

Lower-level modules do not import higher-level ones. `parse` does not
know about `fetch`. `fetch` does not know about `annotate`. `cli`
depends on everything; nothing depends on `cli`.

### 2.4 Why `src/` layout?

Two reasons. It prevents accidental imports from the project root
during development. It forces the package to be installed before
importing, which surfaces hidden dependencies early.

### 2.5 Why dataclasses instead of dictionaries for the data models?

Type safety, immutability, and better IDE support. A misspelled field
on a dataclass raises an error during development. The same mistake on
a dictionary produces a silent `None` at runtime.

### 2.6 How would a new annotation source be added?

Three changes, none invasive. Add the source to `_SOURCES` and
`_BASE_URLS` in `fetch.py`, with its parameter builder. Merge its
fields into `AnnotationResult` in `annotate.py`. If it carries linked
PMIDs, feed them into `golden.py`. Everything else remains untouched.

---

## Section 3: Data

### 3.1 Why ClinVar?

It is the official NCBI archive of variant interpretations. It provides
classification, review status, phenotype, and citations to PubMed. All
of it is free and open.

### 3.2 Why move from the API to bulk tables?

Two concrete failures. The elink endpoint returned HTTP 429 under
ordinary load even below the documented three requests per second. The
efetch endpoint returned HTTP 414 for variants with more than a few
dozen linked publications, because the identifier list made the
request URL too long.

The bulk tables remove both problems. One download, then local reads.
The change also makes the pipeline reproducible, because the input is
a versioned file.

### 3.3 Which bulk files are used?

Two files from `tab_delimited`:

- `variant_summary.txt.gz` — the full catalogue
- `var_citations.txt` — the PubMed linkage

Note that the second file is published without gzip compression. This
was discovered during development, not from the documentation.

### 3.4 How is a variant matched against ClinVar?

The `Name` column carries the HGVS string. A regex extracts the `c.`
part. Two keys are produced for each variant: the exact string and a
shortened form with trailing nucleotide letters removed. Lookup tries
both.

### 3.5 Why is tolerant matching necessary?

The HGVS convention changed. Older records wrote the deleted
nucleotides out: `c.68_69delAG`. Current ClinVar records use the
shorter form `c.68_69del`. Exact matching would miss five of the ten
source variants. With the shortened form accepted, eight match.

### 3.6 Why were two variants dropped?

`hbb_c20a_t` and `g6pd_c563c_t` do not appear in the current ClinVar
export under any form that the source table uses. HBB at position 20
is recorded as `c.20A>C`, a different substitution. The two variants
are excluded from the benchmark and the exclusion is reported at the
end of every run.

### 3.7 What is the alias column for?

Papers rarely write the full HGVS form. The CFTR variant
`c.1521_1523delCTT` is almost always written F508del. The APOE variant
`c.388T>C` is written e4. CYP2C19 `c.681G>A` is written CYP2C19*2.

The alias column lists these alternate names. They are combined with
the HGVS tokens when deciding whether a passage is relevant. This
change grew the total reference set from roughly thirty publications
to 325.

### 3.8 How is the bulk file read without exhausting memory?

The summary file has about nine million rows. It is read line by line,
and a filter is applied during the read. Only variants whose gene and
HGVS match the source table are kept. The output dictionary contains
at most a few dozen entries.

### 3.9 What happens if ClinVar changes the file format?

Three layers of protection. `csv.DictReader` keys on column names, not
positions, so reordering columns is harmless. The citations parser
accepts multiple column names for the PubMed identifier
(`citation_id`, `PubMedID`, `pmid`). The benchmark reports when zero
variants match, which makes a format change obvious in the log.

---

## Section 4: Evaluation

### 4.1 How does the benchmark work?

It reads the evidence files, keeps the ones with a non-empty reference
set, builds a corpus from the union of candidate PMIDs, and runs three
retrieval strategies against it. Four metrics are computed per
strategy: Recall@5, Recall@10, MRR, and nDCG@10.

### 4.2 What is the difference between reference and candidate?

Reference PMIDs are the ClinVar-linked publications that matched the
variant token filter. They are the ground truth for the metrics.
Candidate PMIDs are the union of reference PMIDs and PubMed search
results. They form the retrieval corpus. Candidate minus reference
gives the distractors.

### 4.3 Why is this separation important?

Without distractors, every strategy would retrieve the same small set
of documents and Recall would be trivially one. The distractors make
the task non-trivial and the metrics meaningful.

### 4.4 Why these four metrics?

They are standard in information retrieval. Recall@K measures how many
relevant items reach the top K. MRR measures the position of the first
relevant item. nDCG@10 is rank-aware and weights higher positions more
heavily. Together they describe different aspects of quality.

### 4.5 Why is Dense better than BM25?

BM25 matches terms. Dense retrieval with PubMedBERT matches meaning.
In biomedical text, the same concept appears under many terms, and
HGVS notation rarely appears in papers. PubMedBERT handles this better.

The measured difference: nDCG@10 improves by roughly 1.85 times, and
Recall@10 by about 44 percent.

### 4.6 Why is Hybrid worse than Dense?

RRF with equal weighting gives the same influence to BM25 and dense.
On this corpus BM25 is weaker, so the equal weighting pulls the
hybrid result toward BM25. The result sits close to BM25 rather than
close to dense.

An asymmetric weighting scheme would likely improve this. It is listed
as a Phase 2 addition. The current result is reported as measured,
without tuning to make the number look better.

### 4.7 Why are the absolute numbers low?

Two reasons. The reference sets are large. BRCA1 alone has 65 reference
PMIDs, so even a perfect ranking can only place 5/65 in the top five.
And the vocabulary gap between HGVS and literature is wide. The alias
list reduces it but does not eliminate it.

### 4.8 Why MRR is nearly identical across strategies?

The first relevant item usually appears at rank 2 or 3 regardless of
strategy. MRR is sensitive only to that first position. On a corpus of
963 passages, all three strategies manage to put something relevant
near the top. The differences show up in the full ranking, which is
what nDCG@10 measures.

### 4.9 What would improve the benchmark?

Three things. A larger golden set, currently eight variants. Graded
relevance rather than binary. Additional sources such as bioRxiv and
medRxiv. All three are documented as Phase 2 additions.

### 4.10 Why store results in the repository?

Reproducibility. The JSON file and the two plots are regenerated on
every change to the retrieval code or the golden set. The history of
results is available through git. A regression in a metric becomes
visible in the commit log.

---

## Section 5: Engineering practice

### 5.1 How is the test suite organized?

By module. Each module has a matching test file. Network calls are
replaced with mocks, so no test touches NCBI or PubMed. The full suite
runs in about ten seconds.

### 5.2 Why mock the network?

Speed, stability, and independence from the internet. A test that
depends on NCBI fails when NCBI is slow or rate-limits, which says
nothing about the code.

### 5.3 Why CI on three Python versions?

The project claims support for 3.10 and above. CI must verify that
claim. Three versions catch accidental use of newer syntax.

### 5.4 Why Docker when the tool is a CLI?

Two reasons. Users who do not want to install Python and dependencies
on their own machine. Deployments in restricted environments that do
not permit installing packages from the internet.

### 5.5 How are commits organized?

One change per commit. Messages in English, descriptive rather than
generic. Examples:

- `Fix ClinVar citations filename`
- `Add alias support to variant tokens`
- `Cache corpus embeddings across queries`

A reader of `git log` should be able to follow what happened without
opening the code.

### 5.6 Why is continuous benchmarking set up?

Any change to the retrieval code or the golden set triggers a benchmark
run. The results are committed automatically. This makes regressions
visible immediately and gives the project a running record of how the
metrics evolve.

### 5.7 How does the workflow avoid rate limits on PubMed?

Three things. PubMed requests are batched into groups of fifty. The
default pause between requests is one second, which is one third of
the documented rate limit. Every response is cached, so repeated runs
do not touch the network.

### 5.8 What happens if a workflow push fails?

The commit step runs `git pull --rebase` before `git push`. If a
previous run has pushed changes in the meantime, the rebase applies
them first. This handles the race condition that occurs when two runs
finish at the same time.

---

## Section 6: General research software questions

### 6.1 What makes this a research software project rather than a machine learning project?

The goal is a tool, not a model. The project includes tests, CI,
Docker, documentation, and a documented interface between modules. The
embedding model is one component, not the center of the project.

### 6.2 How is reproducibility achieved?

Versioned bulk data. Cached network responses. Deterministic
algorithms. A benchmark that runs from committed artifacts. All of
these together mean that a new clone of the repository can reproduce
the same numbers.

### 6.3 What are the main engineering challenges?

The migration from API to bulk data, because it touched several
modules and required debugging of external contracts. Tolerant HGVS
matching, because the difference between `c.68_69delAG` and
`c.68_69del` is not obvious until the data is inspected. Alias-aware
relevance, because the vocabulary gap between clinical notation and
biomedical literature is wide.

### 6.4 What are the known weaknesses?

Small golden set. Binary relevance labels. Hybrid underperforming
dense. Corpus that fits in memory, which will not scale to tens of
thousands of variants. All are documented in the Limitations section.

### 6.5 What would the next phase add?

Expansion of the golden set to fifty variants. Graded relevance.
Additional retrieval sources. Asymmetric RRF weighting. These are
listed in `docs/evaluation.md`.

### 6.6 How would this scale?

Three bottlenecks. Memory, because the corpus is held in memory. Time,
because dense retrieval on CPU is slow. Data, because the ClinVar bulk
files are large and downloaded on every fresh environment. The
solutions are a vector database, a GPU or a smaller model, and
persistent caching.

### 6.7 How is the project documented?

Four documents. `README.md` for orientation. `docs/architecture.md`
for module structure. `docs/evaluation.md` for the benchmark design
and results. `docs/design_qa.md`, this document, for the reasoning
behind specific choices.

### 6.8 What is intentionally not done?

No clinical validation. No claim of diagnostic accuracy. No support
for structural variants. No integration with electronic health
records. All of these are out of scope for a research tool.
