# Case Study — Student Engagement API

**Repository:** [student-engagement-api](https://github.com/Freddricklogan/student-engagement-api) · **Live demo:** [ghcr.io/freddricklogan/student-engagement-api](https://github.com/Freddricklogan/student-engagement-api/pkgs/container/student-engagement-api) (container image; a hosted URL is not yet provisioned) · **Author:** Freddrick Logan

---

## 1. Who has this problem

A dean of students, an advising office, or a programme like Elevate at Illinois Tech that is accountable for retention and has the data to act on it — page views, video watch time, quiz attempts, discussion posts — sitting in a warehouse nobody queries until the term is over. The same shape exists anywhere with a rich event stream and no governed interface over it: customer-success teams, workforce programmes, public-sector service portals.

## 2. The problem, as a scenario

Week six. An advisor gets a withdrawal notice for a first-generation student who stopped watching lecture videos in week two, stopped posting in week three, and missed two quizzes in week four. Every signal was logged. None was queryable, because the only interface was a dashboard whose API key was hard-coded, embedded in the JavaScript served to every visitor, accepted in the query string, and granted full write access to the student record. The institution could not open that dashboard to advisors without opening the record to anyone who viewed the page source.

## 3. What it costs to leave it alone

Two costs pulling in opposite directions. Students the institution could have reached are lost at exactly the moment the data would have flagged them; retention is a funded metric for programmes like mine, and every avoidable withdrawal is a person and a budget line. Against that, an insecure interface over student data is a compliance exposure: FERPA obligations are described by the U.S. Department of Education ([studentprivacy.ed.gov](https://studentprivacy.ed.gov/)), and a breach of education records is the kind of incident that ends programmes. Leaving it alone means choosing between the two; a governed interface removes the choice.

## 4. The approach, and the alternative I rejected

I rebuilt the service as an async FastAPI application around three commitments. Least privilege: OAuth2 password grant issuing short-lived JWTs with verified issuer and audience, three roles — viewer, analyst, admin — and every write endpoint gated, so the public demo account cannot change a row. Every failure debuggable: one centralised error path emitting RFC 9457 problem documents, with an `X-Request-ID` on every response that also appears in the structured JSON log line. Engagement as a modelled concept: the old API stored whatever number a caller posted; scoring is now a tested domain service weighting event quality, participation breadth and recency, inspectable per student.

The alternative I rejected was to patch the Flask application — rotate the key, remove the debugger, add a role check. That closes the headline findings and leaves the architecture that produced them: no validation layer, no error contract, blocking I/O, N+1 queries in the model. Fifty findings in the audit file argue for a rebuild, and a hexagonal layout — domain, application, adapters, infrastructure — is what keeps each of them fixed.

## 5. What the code does today

Real: the authentication and role model, validated request and response schemas, the scoring service, the analytics endpoints, the problem-details error path, request correlation and structured logging, rate limiting, health and readiness probes, a multi-stage non-root container, and byte-identical responses on every legacy `/api/*` path, asserted by a test.

Simulated: the data. With `DEMO_MODE=true` the service seeds a deterministic synthetic dataset and creates three demo accounts with public, documented passwords; there is no integration with a real learning-management system. No hosted URL has been provisioned yet; the container image is published and both hosting blueprints are committed.

Worth knowing: the audit file catalogues the earlier version's fifty findings with file references — seven in authentication alone — and the compatibility commitments the rebuild honoured so no existing URL broke.

## 6. Evidence

Measured in continuous integration on the current main branch: 146 tests passing; 98% combined statement and branch coverage over the application package; `ruff` clean; `mypy --strict` clean across 45 source files; `bandit` with no issues identified; `pip-audit` with no known vulnerabilities; the container image built and scanned by Trivy before it is pushed to the GitHub Container Registry. The scoring weights — 60% quality, 20% breadth, 20% recency — are constants in `app/application/scoring.py` with their own test module.

## 7. What it would take to run this in production

The gap here is integration rather than engineering. It would need: an ingest path from the learning-management system — xAPI or IMS Caliper statements rather than a seed script; PostgreSQL in place of SQLite, which the async SQLAlchemy layer already anticipates; identity from campus single sign-on rather than a local user table; a retention and access policy agreed with the registrar before any advisor sees a name; and OpenTelemetry traces alongside the logs. Hosting is one small container and a managed database. Rough effort: ingest and policy dominate, a few weeks each, with the policy conversation the longer.

## 8. Limits and next steps

SQLite and a single instance; no ingest from a real event source; a scoring model that is transparent but not yet validated against outcomes, which it must be before anyone acts on it. Next steps, in order: deploy the committed Fly configuration so the demo has a URL; the PostgreSQL profile; xAPI ingest; and a validation study of the score against retention data, under an institutional review, before it informs an advising decision.

## 9. Who should look at this

**Hiring manager:** evidence that I can take a service with a hard-coded credential in its front-end and rebuild it to least privilege, with numbers.
**Consulting client:** a reference for what a governed learning-analytics interface looks like — and a candid statement of the policy work that has to precede it.
**Engineer:** read `app/application/scoring.py` and `app/adapters/api/` for the domain service and the RBAC dependencies, `tests/test_rbac.py` for how the role boundary is asserted, and the audit file for the fifty reasons this was a rebuild.
