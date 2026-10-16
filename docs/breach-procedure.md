# Personal data breach procedure (TR-S-08)

**Status: draft.** It has not been reviewed by the institution's data protection contact, who must confirm the legal
duties, the regulator's reporting channel and the deadlines before this procedure is relied on. The TRD (section 8 and
source 11) records that law-firm summaries of India's data-protection rules, notified on 13 Nov 2025, describe breach
reporting duties applying from 13 May 2027 and a report within 72 hours. That is orientation, not legal advice.

## Who does what

Fill in these names before any use with real students.

| Role | Name | How to reach them | Deputy |
| --- | --- | --- | --- |
| Incident lead (runs this procedure, keeps the timeline) | ________ | ________ | ________ |
| Data protection contact (decides on and sends the notices) | ________ | ________ | ________ |
| System operator (has shell access to the host) | ________ | ________ | ________ |
| Regulator reporting channel (confirmed by the data protection contact) | ________ | ________ | |

## What counts as a breach here

Any unauthorised access to, disclosure of, change to or loss of personal data the system holds: accounts (email,
password hash), submissions (code and run results), chat messages, placement answers, mastery and its ledger, consent
records, and the audit trail itself (it holds IP addresses). Examples: a student reading another student's submission,
a stolen instructor password used to export a class, a database dump left on a shared drive, a leaked `.env` file.

## Timeline

Hour 0 is when anyone in the team first has a reason to think a breach may have happened. Write that time down.

| By | Step |
| --- | --- |
| Hour 0 | Tell the incident lead. Start a written timeline (what was seen, when, by whom). Do not delete anything. |
| Hour 1 | **Preserve evidence** (below). Container logs are lost when containers are rebuilt, so copy them first. |
| Hour 2 | **Contain** (below): stop the leak without destroying evidence. |
| Hour 4 | **Scope** with the breach report: what happened, since when, which students. |
| Hour 24 | Incident lead and data protection contact decide whether this is a reportable breach and who must be told. |
| Hour 72 | Report to the regulator through the confirmed channel, and tell affected students, as the contact directs. Send what is known; say what is still being checked and when the update will follow. |
| After | Fix the cause, add a test that would have caught it, and record the review in the timeline. |

## 1. Preserve evidence

Run these from the `LMS-Portal` folder before any restart or rebuild:

```sh
mkdir -p backup/incident-$(date -u +%Y%m%dT%H%MZ) && cd backup/incident-*
docker compose logs --no-color --timestamps > container-logs.txt
docker compose exec -T db pg_dump -U lms_owner -Fc lms > database.dump
```

`backup/` is git-ignored; these files hold personal data, so keep them only on the incident lead's machine.

## 2. Scope with the breach report

```sh
docker compose exec -T api python -m app.breach_report --since 2026-10-01T00:00 > breach-report.json
```

Use a start time well before the first sign. The report lists, for the window:

- addresses and accounts with many failed logins, and any successful login from such an address (a possible takeover);
- accounts with many refused or not-found reads of other students' records, with the paths they tried;
- every export of a class's mastery data, by whom and from where;
- staff accounts created, and erasures;
- the student numbers possibly affected: owners of probed submissions and students in exported courses.

The audit trail (`audit_events`) records logins, failed logins, refused (401, 403) and throttled (429) requests,
not-found reads of submission and history ids, exports, staff accounts created, consent changes and erasures, each with
the user number, IP address, request id and time. It holds no passwords, tokens, email addresses, code or messages; a
failed login stores a keyed hash of the email, so repeated attempts on one account can be counted. Match a request id
with the container log copied in step 1 for the full request line. To turn student numbers into the email addresses a
notice needs, the operator queries the `users` table; that list goes only to the data protection contact.

## 3. Contain

Pick what fits the incident; each step is logged in the timeline with its time.

- **Stop all access:** `docker compose stop api frontend`.
- **Log everyone out:** change `JWT_SECRET` in `.env` and run `docker compose up -d`. Every token stops working.
- **One account taken over:** reset its password with the operator's database access, then change `JWT_SECRET`.
- **Database or service credentials exposed:** change `POSTGRES_PASSWORD`, `LMS_API_DB_PASSWORD`,
  `LMS_MASTERY_DB_PASSWORD`, `LMS_CHAT_DB_PASSWORD`, `REDIS_PASSWORD` and `MASTERY_SERVICE_TOKEN`; the role passwords
  must also be changed inside PostgreSQL (`ALTER ROLE ... PASSWORD ...`) before the restart.
- **Model provider key exposed:** revoke it at the provider and replace it in `.env`.
- **A dump or export file leaked:** find where it went, ask for it to be deleted, and record who confirmed.

## 4. Notices

The data protection contact decides who receives which notice and through which channel; these are starting points.

**To the regulator** (send what is known by hour 72; mark unknowns as "being checked"):

- Organisation, and the data protection contact's name and details.
- What happened and how it was found; when it started, when it was found, when it was contained.
- What personal data was involved (from the list above) and roughly how many students.
- Likely consequences for the students.
- What has been done to contain it and to stop it happening again.
- When the next update will follow.

**To each affected student** (plain language):

> On [date] we found that [what happened]. It involved your [which data]. It did not involve [what was not affected].
> We have [what was done]. You may want to [practical steps, for example change a password used elsewhere].
> If you have questions, contact [data protection contact]. We will tell you if we learn more.

## 5. Evidence kept

The timeline, the copied container logs, the database dump, the breach report, the notices as sent with their times,
and the review. Keep them for as long as the data protection contact directs, then delete them.
