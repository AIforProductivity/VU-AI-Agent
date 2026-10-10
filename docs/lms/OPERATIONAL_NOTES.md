# VU LMS — Operational Notes

> Source: system operator (user-provided), 2026-10. These are cadence rules
> for what changes inside VULMS — the MCP serves them as static knowledge;
> the AGENTS read live values when a student pastes a page.

## Dynamic Sources and Their Cadence

| Source | Update cadence | Notes |
|--------|----------------|-------|
| **Notice Board** | Daily | Announcements per course + university-wide |
| **To Do Calendar** | Daily | Every activity carries a deadline window |
| **Academic Calendar** | Occasional | Semester start/end, holidays — changes rarely |
| **Date Sheet** | Seasonal | See below + handbook "Conduct of Examination" |

## To Do Calendar — Typical Deadline Windows

Every activity in the To Do Calendar has an attempt window after it opens:

| Activity | Window to attempt |
|----------|-------------------|
| Quiz | ~2 days |
| Assignment | 4 to 5 days |
| GDB | 2 to 3 days |

Practicals may also appear with their own windows.

## Date Sheet

- Creation portal: https://datesheet.vu.edu.pk/
- Opens ~8–14 days before exams start; late setup (last week) carries a fee
- Campus selection is the student's decision; papers are then scheduled in
  slots across 12–16 exam days
- Missed/unplanned papers: rescheduled ~4–7 days after normal exams end
  (a paper missed on its date can be arranged within 24 hours); all
  rescheduled papers sit on ONE day in multiple university-allocated slots
- Results: published ~12–16 days after exams end — CGPA/courses first,
  then subject scores; grade book updates the day after initial results;
  on-campus students can get complete results from their campus on results
  day (10 AM–12 PM)

## Handling Live Values

The values themselves (today's Notice Board items, this week's deadlines)
are NEVER served by the MCP — they live in the student's logged-in session.
Ask the student to copy the page (Ctrl+A, Ctrl+C, Ctrl+V) and use the paste
ingestion pipeline; the windows above are the priors an agent reasons with.
