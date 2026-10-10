# VU LMS Reverse Engineering Guide

> **Purpose:** Document the complete structure of VU LMS to help students navigate and use it effectively.
> **LMS URL:** https://vulms.vu.edu.pk
> **Last Updated:** 2026-10-10

---

## Table of Contents

1. [Home Dashboard](#home-dashboard)
2. [Course Pages](#course-pages)
3. [To Do / Calendar](#to-do--calendar)
4. [Grade Book](#grade-book)
5. [Account Book](#account-book)
6. [Progress](#progress)
7. [Lecture Schedule](#lecture-schedule)
8. [Mail](#mail)
9. [Notes](#notes)
10. [My Study Scheme](#my-study-scheme)
11. [My Studied Courses](#my-studied-courses)
12. [e-ID Card](#e-id-card)
13. [Student Services](#student-services)
14. [Course Selection](#course-selection)
15. [Help / Support System](#help--support-system)

---

## Home Dashboard

**URL:** `https://vulms.vu.edu.pk/Home.aspx`

### User Info Displayed
- **Name:** `<STUDENT_NAME>`
- **Student ID:** `<STUDENT_ID>` (format: XX000000000 — letters + digits)
- **Program:** `<PROGRAM_NAME>`
- **Profile Picture:** `https://vulms.vu.edu.pk/Profile/GridImageTemplate.aspx`

### Navigation Menu (Sidebar)

| Menu Item | PostBack Command | Description |
|-----------|----------------|-------------|
| Home | `__doPostBack('ctl00$lbtnHome','')` | Main dashboard |
| To Do Calendar | `__doPostBack('ctl00$lbtnActivityCalendar','')` | Upcoming deadlines |
| Grade Book | `__doPostBack('ctl00$lbtnGradeBook','')` | All grades |
| Account Book | `__doPostBack('ctl00$lbtnAccountBook','')` | Financial records |
| Progress | `__doPostBack('ctl00$lbtnProgressTimeline','')` | Academic progress |
| Lecture Schedule | `__doPostBack('ctl00$lbtnLectureSchedule','')` | Class schedule |
| Mail | `https://gmail.vu.edu.pk/` | VU Gmail (external) |
| Notes | `__doPostBack('ctl00$lbtnPersonalDiary','')` | Personal diary |
| My Study Scheme | `__doPostBack('ctl00$lbtnMyStudyScheme','')` | Degree plan |
| My Studied Courses | `__doPostBack('ctl00$lbtnMyStudiedCourses','')` | Completed courses |
| e-ID Card | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/PrintStudentECardView.aspx` | Print ID card |
| Student Services | `__doPostBack('ctl00$lbtnStudentServices','')` | Admin services |
| Course Selection | `__doPostBack('ctl00$lbtnCourseSelection','')` | Add/drop courses |
| Contact Us | `http://www.vu.edu.pk/contact.aspx` | VU contact |
| Help | `https://www.vu.edu.pk/SupportSystem/` | Support system |

### Top Bar Links
- **My Profile:** `https://vulms.vu.edu.pk/Profile/StudentProfile.aspx`
- **Change Password:** `https://vulms.vu.edu.pk/Settings/ChangePassword.aspx`
- **My Logins History:** `https://vulms.vu.edu.pk/Settings/MyLogins.aspx`
- **Logout:** `__doPostBack('ctl00$lnkLogout','')`

### Alert Messages Section
- Displayed in `div#MainContent_divShowAlerts`
- Shows system-wide announcements (e.g., course selection deadlines)

### Course List Section
- Container: `div#MainContent_divCourseList`
- Each course in `div#divCourse` (class: col-12)
- Course button: `ibtnCourseHome` in grid `gvCourseList`

### Course Data Pattern
- Course images: `https://vulms.vu.edu.pk/Courses/{COURSE_CODE}/Common/{COURSE_CODE}_Instructor.jpg`
- Course home button: `__doPostBack('ctl00$MainContent$gvCourseList$ctl${ROW_NUM}$ibtnCourseHome','')`

### Per-Course Sub-Sections (Links available for each course)
- **Assignments** — View/submit assignments
- **GDB** — Graduate Discussion Board (post/view discussions)
- **Quiz** — Take quizzes
- **Activity** — Course activities
- **Announcements** — Instructor announcements (badge shows count)

---

## Course Pages

**URL:** `https://vulms.vu.edu.pk/CourseHome.aspx`
**Access:** Click any course from Home → navigates to CourseHome.aspx

### Course Header
- Course name + code (e.g., "CS408 - Human Computer Interaction")
- Instructor name + qualifications
- Instructor photo: `https://vulms.vu.edu.pk/Courses/{CODE}/Common/{CODE}_Instructor.jpg`
- Instructor biography modal available

### Course Navigation Tabs (PostBack Buttons)

| Tab | Button ID | Content |
|-----|-----------|---------|
| Index / Lesson | `MainContent_btnliIndexPB` | Weekly lesson schedule (default view) |
| Course Information | `MainContent_btnliOverviewPB` | Course overview/details |
| FAQs | `MainContent_btnFAQsPB` | Frequently asked questions |
| Glossary | `MainContent_btnGlossaryPB` | Course terminology |
| Books | `MainContent_btnBooksPB` | Reference books |
| Download Files | `MainContent_btnDownloadFilesPB` | Downloadable resources |
| Internet Links | `MainContent_btnInternetLinksPB` | External links |
| Assessment Scheme | `MainContent_btnGradingSchemePB` | Grading breakdown |

### Weekly Schedule / Lesson Index (Default View)
- Container: `div#MainContent_divIndex`
- Table: `MainContent_lstWeeklySchedule` with rows per week
- Each week has multiple lessons (typically 3 per week)
- Lesson button: `__doPostBack('ctl00$MainContent$lstWeeklySchedule$ctrl${WEEK}$rptIndex$ctrl${LESSON}$lbtnViewLesson','')`
- Each lesson shows: Week #, Lesson Title, Status (Closed/Opened), Marks (N/A or score)

### Lesson Status Types
- **Closed** — Not yet available (future lessons)
- **Opened** — Currently available to view/submit

### Course Information Tab Structure
- **Course Code + Title**
- **Category** (e.g., Computer Science/Information Technology)
- **Credit Hours** (e.g., 3 Credit Hours)
- **Course Synopsis** — Brief description of course content
- **Learning Outcomes** — List of expected outcomes
- **Course Contents** — Full list of topics/units

### FAQs Tab Structure
- List of frequently asked questions
- Questions cover course concepts, definitions, and key topics

### Glossary Tab Structure
- A-Z index with alphabetical navigation (A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z, All)
- Each term has a detailed definition
- Terms cover course-specific vocabulary and concepts

### Books Tab Structure
| Field | Description |
|-------|-------------|
| Title | Book title |
| Citation | Full citation (Author, Year) |
| Author | Author name(s) |
| Edition | Edition number |
| Publisher | Publishing company |

### Download Files Tab Structure
| Field | Description |
|-------|-------------|
| File Name | Name of downloadable file |
| File Size | Size in KB/MB |
| Last Updated | Date of last update |

### Internet Links Tab Structure
| Field | Description |
|-------|-------------|
| URL | External link |
| Description | What the link provides |

### Assessment Scheme Tab
- Tab loads but content area may be empty (no grading breakdown displayed for some courses)

### Course Page Navigation Pattern
- Clicking a course from Home → `CourseHome.aspx` (shows Index/Lesson tab by default)
- Each tab is a PostBack button (no URL change, same page)
- "Back" link returns to `Home.aspx`
- Sidebar navigation remains consistent across all pages

---

## To Do / Calendar

**URL:** `https://vulms.vu.edu.pk/ActivityCalendar/ActivityCalendar.aspx`
**Access:** Sidebar → "To Do Calendar"

### Two Views (Tabbed)

| View | PostBack | Description |
|------|----------|-------------|
| To Do Calendar | `__doPostBack('ctl00$MainContent$tabHCalendar','')` | Calendar view (default) |
| Classic To Do | `__doPostBack('ctl00$MainContent$tabHClassic','')` | List view |

### Calendar View
- Uses **FullCalendar** JS library (`div#calendar`, class: `fc fc-ltr fc-unthemed`)
- Navigation buttons: **today**, **month**, **week**, **day**
- Shows current month with events (assignments, quizzes, GDBs due)
- Events are color-coded by type

### Classic To Do View
- Container: `div#tabCClassic`
- Shows list of pending items by category:
  - **Assignments** — Pending submissions
  - **Quizzes** — Upcoming/active quizzes
  - **Graded Discussion Board (GDB)** — Discussion board posts due
  - **Practicals** — Pending practicals

### Key Divs
- `div#MainContent_divMain` — Main container
- `div#tabCCalendar` — Calendar tab pane (active by default)
- `div#tabCClassic` — Classic list tab pane

---

## Grade Book

**URL:** `https://vulms.vu.edu.pk/GradeBook/GradeBook.aspx`
**Access:** Sidebar → "Grade Book"

### Five Tabs (Anchor Links on Same Page)

| Tab | Section ID | Description |
|-----|-----------|-------------|
| Student Grade Book | `StudentGradeBook` | All course grades by semester |
| Midterm Result (FALL 2026) | `MidtermResult` | Midterm exam results (default active) |
| Grading Scheme | `GradingScheme` | Grade boundaries and points |
| Projected CGPA Calculator | `CGPACalculator` | Calculate projected CGPA |
| COUM/DAC | `RLManagement` | Charge sheet / Statement of allegations |

### Student Grade Book Tab
- Container: `div#MainContent_divRegular`
- Header: `div#MainContent_divGBHeaderSection`
- Shows: Semester, Course list with grades
- Grade columns: Name, Grade, Grade Points, etc.

### Midterm Result Tab
- Container: `div#MainContent_divMidtermHeading`
- Shows midterm exam results for current semester
- "No Record Found!" if no midterm results yet

### Grading Scheme Tab
- Container: `div#MainContent_pnlgradingscheme`
- Shows grade boundaries (A, B, C, D, F) with grade points

### Projected CGPA Calculator Tab
- Container: `div#MainContent_divCalculator`
- Interactive calculator: select courses, adjust scores → see projected CGPA
- Shows: Degree info, total credits, projected CGPA
- Key divs: `div#mainPanel`, `div#resultBox`

### COUM/DAC Tab
- Container: `div#MainContent_RLControl1_divRLControl`
- Shows charge sheet / statement of allegations
- "View" button: `__doPostBack('ctl00$MainContent$RLControl1$lbtnShowCauseNoticeMessage','')`
- Rules link: `https://vulms.vu.edu.pk/RLManagement/AppealRules.aspx`

---

## Account Book

**URL:** `https://vulms.vu.edu.pk/AccountBook/AccountBook.aspx`
**Access:** Sidebar → "Account Book"

### Overview
- **Title:** "My Account Book"
- Shows all financial transactions (challans) with payment status
- Grid: `div#MainContent_divRecord` (class: `Accounttbl`)
- Each challan in: `div#MainContent_grdaccountbook_pnl_{INDEX}` (alternating class: `AlternativeRowColor`)

### Challan Data Structure

| Field | Description |
|-------|-------------|
| Challan No. | Unique payment ID (numeric) |
| Challan Type | See types below |
| Payable | Amount due (PKR) |
| Paid | Amount paid (PKR) |
| Balance | Remaining balance (0 = fully paid) |
| Due Date | Payment deadline |
| Paid Date | Actual payment date |
| Payment Mode | See modes below |
| Cancelled | Cancellation status |
| Action | Link to view challan details |

### Challan Types
| Type | Description |
|------|-------------|
| `NewAdmission_ProcessFee` | One-time admission processing fee |
| `NewAdmission` | Admission fee |
| `Installments_FS` | Semester fee installments |
| `SocietiesAndSportsFund` | Society/sports fund |
| `EndowmentFund` | Endowment fund |
| `Misc` | Miscellaneous charges |
| `Installments` | Regular installments |

### Payment Modes
| Mode | Description |
|------|-------------|
| `TMFBLOnline` | TMBL online payment |
| `HBLIPG` | HBL internet payment gateway |
| `ChallanForm` | Physical challan form |
| `InternalTransfer` | Internal transfer |
| `BAFLIPG` | BAFL internet payment gateway |
| `ABLOnline` | ABL online payment |

### Viewing a Challan
- Click challan number → PostBack: `WebForm_DoPostBackWithOptions(new WebForm_PostBackOptions("ctl00$MainContent$grdaccountbook$ctl${ROW}$ibtnchallan", ...))`
- Upload button: `MainContent_ibtnUpload`
- Cancel button: `MainContent_ibtnCancel`

### Summary
- Total Payable Amount shown at bottom (Rs / $)

---

## Progress

**URL:** `https://vulms.vu.edu.pk/ProgressTimeline/ProgressTimeline.aspx`
**Access:** Sidebar → "Progress"

### Overview
- **Title:** "Progress Timeline"
- Shows academic progress for each course in tabbed view
- Each course has its own tab with progress metrics

### Course Tabs
- Container: `div#MainContent_udpProgress`
- Tab header: `MainContent_lstTabHeader` with per-course tabs
- Tab content: `div#tabContent{COURSE_CODE_LOWER}` (e.g., `tabContentcs202`)
- Tab button: `__doPostBack('ctl00$MainContent$lstTabHeader$ctrl${INDEX}$tabHeadercs${CODE}','')`

### Per-Course Progress Metrics

| Metric | Section ID Pattern | Description |
|--------|-------------------|-------------|
| Graded Activities | `divGradedActivities` | Assignments, GDBs, Quizzes |
| Attendance | `divAttendance` | Class attendance record |
| Participation | `divParticipation` | MDB participation |
| Course Content Completion | `divLearning{CODE}` | Weekly learning progress |
| MDB Participation | `divParticipation{CODE}` | Discussion board activity |
| Self-Assessment Score | `divAssessment{CODE}` | Self-assessment results |

### Graded Activities Sub-Sections
- **Assignments** — Assignment scores
- **GDB** — Graded discussion board scores
- **Quizzes** — Quiz scores

### Data Storage
- Learning activity data stored in hidden field: `hfLearningActivityData{CODE}`
- Participation data stored in hidden field: `hfParticipationData{CODE}`
- Data is JSON-parsed and rendered as charts/visualizations

### Key Divs
- `div#MainContent_divMain` — Main container
- `div#tabContent{CODE}` — Per-course tab pane
- `div#divLearning{CODE}` — Course content completion chart
- `div#divParticipation{CODE}` — MDB participation chart
- `div#divAssessment{CODE}` — Self-assessment score chart

---

## Lecture Schedule

**URL:** `https://vulms.vu.edu.pk/LectureSchedule/LectureSchedule.aspx`
**Access:** Sidebar → "Lecture Schedule"

### Overview
- **Title:** "Weekly Lecture Schedule"
- Shows weekly class/lecture schedule for the student
- May show "schedule not available" message if not published yet
- Container: `div#MainContent_divShowAlerts`

### Key Notes
- Schedule is published by VU and may not be available at all times
- Shows lecture timings, venues (virtual/physical), and course slots
- Student ID is referenced in availability messages

---

## Mail

**URL:** `https://gmail.vu.edu.pk/`
**Access:** Sidebar → "Mail" (opens in new tab)

### Overview
- VU-provided Gmail account for students
- Opens in new browser tab
- Full Gmail interface with VU branding

---

## Notes

**URL:** `https://vulms.vu.edu.pk/PersonalDiary/Notes.aspx`
**Access:** Sidebar → "Notes"

### Overview
- **Title:** "Notes"
- Personal diary/notes feature for students
- Shows current date
- Page appears mostly empty by default — notes are likely loaded dynamically or added via UI not captured in static content
- No visible buttons or links beyond standard navigation

---

## My Study Scheme

**URL:** `https://vulms.vu.edu.pk/GradeBook/MyStudyScheme.aspx`
**Access:** Sidebar → "My Study Scheme"

### Overview
- **Title:** "My Study Scheme"
- Shows complete degree plan with all semesters
- Displays: Degree, Program, Version, and all courses by semester

### Student Degree Info Structure
- **Degree:** `<DEGREE_NAME>` (e.g., BS)
- **Program:** `<PROGRAM_NAME>` (e.g., Software Engineering)
- **Version:** `<VERSION>` (e.g., Fall 2024 (2404))

### Study Scheme Table Structure

| Column | Description |
|--------|-------------|
| Code | Course code (e.g., CS101) |
| Title | Course name |
| Category | — |
| Sub Category | — |
| Type | Required / Elective / Deficiency |
| Course Type | Regular / Practical / Project |
| Cr.Hrs. | Credit hours |
| Group | Course group pairing (e.g., CS201CS201P (2)) |
| Specialization | — |
| Status | Studied / Pending / -- (alternative not taken) |

### Status Meanings
- **Studied** — Course completed
- **Pending** — Course not yet taken
- **--** — Alternative course not taken (when paired electives exist)

### Semester Structure
- 8 semesters total for BS programs
- Each semester has 5-8 courses
- Courses are numbered sequentially across semesters

---

## My Studied Courses

**URL:** `https://vulms.vu.edu.pk/MyStudiedCourses.aspx`
**Access:** Sidebar → "My Studied Courses"

### Overview
- **Title:** "My Studied Courses"
- Shows all completed courses with instructor details
- Same course card layout as Home page
- Container: `div#MainContent_divCourseList`
- Each course clickable → PostBack: `__doPostBack('ctl00$MainContent$gvCourseList$ctl${ROW}$ibtnCourseHome','')`

### Course Card Structure
Each course card shows:
- Course code + title
- Department/Category
- Credit hours
- Instructor name
- Instructor qualifications
- Instructor photo: `https://vulms.vu.edu.pk/Courses/{CODE}/Common/{CODE}_Instructor.jpg`

---

## e-ID Card

**URL:** `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/PrintStudentECardView.aspx`
**Access:** Sidebar → "e-ID Card"

### Overview
- **Title:** e-ID Card (Registrar Office)
- Printable student ID card view
- Page loads but main content area appears empty in browser — likely a printable document view
- May require print dialog or specific rendering to display the actual ID card
- No visible buttons or interactive elements beyond standard navigation

---

## Student Services

**URL:** `https://vulms.vu.edu.pk/StudentServices/StudentServices.aspx`
**Access:** Sidebar → "Student Services"

### Overview
- **Title:** "Student Services"
- Organized into 4 categories: Academics, Accounts, Examinations Department, Registrar Office

### Academics (External Links — open in new window)
| Service | URL | Target |
|---------|-----|--------|
| HEC Digital Library | `http://library.vu.edu.pk/cgi-bin/nph-proxy.cgi` | _New |
| Student Hand Book | `http://handbook.vu.edu.pk/` | _New |

### Accounts (LMS Forms — same window)
| Service | URL |
|---------|-----|
| Need Based Scholarship | `https://vulms.vu.edu.pk/StudentServices/Accounts/ScholarshipForm.aspx` |
| Security Refund | `https://vulms.vu.edu.pk/StudentServices/Accounts/SecurityRefundRequest.aspx` |

### Examinations Department
| Service | URL | Target |
|---------|-----|--------|
| Make your Date Sheet | `http://datesheet.vu.edu.pk/` | _New (External) |
| Apply for Additional Copies of Transcript of Record | `https://vulms.vu.edu.pk/StudentServices/Examinations/ApplyForFinalTranscript.aspx` | Same window |
| Apply for Degree | `https://vulms.vu.edu.pk/StudentServices/Examinations/ApplyForDegree.aspx` | Same window |
| Apply for Partial Transcript | `https://vulms.vu.edu.pk/StudentServices/Examinations/ApplyForPartialTranscript.aspx` | Same window |
| Apply for Rechecking of Papers | `https://vulms.vu.edu.pk/StudentServices/Examinations/ApplyForRechecking.aspx` | Same window |
| Apply for Rescheduling of Papers | `https://vulms.vu.edu.pk/StudentServices/Examinations/ApplyForRescheduling.aspx` | Same window |
| Overseas Examination System | `http://qb.vu.edu.pk/` | _New (External) |

### Registrar Office
| Service | URL | Target |
|---------|-----|--------|
| Admission Withdrawal Request | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/AdmissionWithdrawalRequest.aspx` | Same window |
| Apply for Certificate | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/ApplyForCertificate.aspx` | Same window |
| Campus Change Request | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/CampusChangeRequest.aspx` | Same window |
| Continuation from 2-year (Pass out) to 4-year BS Program | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/Continue4YearService.aspx` | Same window |
| Credit Transfer | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/CreditTransferService.aspx` | Same window |
| Documents Verification (Hope Certificate / Online Result Card) | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/VerifyDocumentsForHopeCertificate.aspx` | Same window |
| Duplicate Id Card Request | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/IDCardRequest.aspx` | Same window |
| Migration Certificate | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/ApplyForMigrationCertificate.aspx` | Same window |
| Profile Picture Change | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/ProfilePictureChangeService.aspx` | Same window |
| Proforma for Disable Students | `http://www.vu.edu.pk/apply/Proforma%20for%20Disable%20Students.pdf` | _New (PDF) |
| Re-Admission Request | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/ReAdmissionRequest.aspx` | Same window |
| Semester Freeze | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/ApplyForSemesterFreeze.aspx` | Same window |
| Semester Unfreeze | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/ApplyForSemesterUNFreeze.aspx` | Same window |
| Student Profile Change | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/StudentProfileChangeService.aspx` | Same window |
| Study Program Conversion | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/StudyProgramChangeService.aspx` | Same window |
| Upload Intermediate Certificate / Part 2 Result | `https://vulms.vu.edu.pk/StudentServices/Registrar%20Office/InterCertificateUpload.aspx` | Same window |

### Service Type Summary
| Type | Count | Behavior |
|------|-------|----------|
| **LMS Forms** (same window) | 18 | Open form within VU LMS |
| **External Links** (new window) | 5 | Redirect to external VU services |
| **PDF Download** | 1 | Proforma for Disable Students |

---

## Course Selection

**URL:** `https://vulms.vu.edu.pk/StudentServices/CourseSelection/CourseSelection.aspx`
**Access:** Sidebar → "Course Selection"

### Overview
- **Title:** "Course Enrollment (<SEMESTER_YEAR>)"
- Shows available courses for enrollment in current/next semester
- Displays student's credit info and eligible courses

### Student Credit Info Displayed
- **Credits Earned:** `<TOTAL_CREDITS_EARNED>`
- **Current Semester No:** `<CURRENT_SEMESTER>`
- **Specialization:** `<SPECIALIZATION>`
- **Credits Exempted:** `<CREDITS_EXEMPTED>`
- **Maximum Credits Limit:** `<MAX_CREDITS_LIMIT>`

### Available Courses Table Structure

| Column | Description |
|--------|-------------|
| Sr.No | Sequential number |
| Course | Course code + title |
| Credits | Credit hours |
| Semester No | Semester number |
| Specialization | Specialization (if any) |
| Course Group Description | Group pairing info (e.g., "You can select maximum 1 Course(s) from the course group CS202CS614") |
| Action | Select/Drop action |

### Action Buttons
- **Post a Ticket** — Submit a ticket for course selection issues
- **Save Selection** (`MainContent_btnsave`) — Save course selection

### Enrollment Rules
- Student may repeat once those courses of previous semester(s) in which s/he had secured lowest grades (B-/C/D only)
- Must acknowledge rules before saving selection
- Course group limits apply (e.g., max 1 from a specific course group)

---

## Help / Support System

**URL:** `https://www.vu.edu.pk/SupportSystem/Home.aspx`
**Access:** Sidebar → "Help" (external site)

### Overview
- **Title:** "Support System"
- External ticketing/support system for VU students
- **Purpose:** Generate tickets in relevant departments, track ticket status, and manage support requests
- Submit tickets to various departments
- Track existing tickets

### Navigation
- **Home:** `https://www.vu.edu.pk/SupportSystem/Home.aspx`
- **My Tickets (<COUNT>):** `https://www.vu.edu.pk/SupportSystem/myTickets.aspx`
- **Logout:** `https://www.vu.edu.pk/SupportSystem/logout.aspx`

### Support Categories (Ticket Types)

| Category | Form ID | Submit Button |
|----------|---------|---------------|
| Course Selection | `form-Course-Selection` | `btnSubmitBlue-Course-Selection` |
| My Courses (Enrolled Courses) | `form-My-Courses` | `btnSubmitBlue-My-Courses` |
| Department of Computer Science | `form-Department-of-Computer-Science` | `btnSubmitBlue-Department-of-Computer-Science` |
| Department of Mass Communication | `form-Department-of-Mass-Communication` | `btnSubmitBlue-Department-of-Mass-Communication` |
| Directorate of Finance | `form-Directorate-of-Finance` | `btnSubmitBlue-Directorate-of-Finance` |
| Examinations | `form-Examinations` | `btnSubmitBlue-Examinations` |
| IT Department | `form-IT-Department` | `btnSubmitBlue-IT-Department` |
| Marketing | `form-Marketing` | `btnSubmitBlue-Marketing` |
| Registrar Office | `form-Registrar-Office` | `btnSubmitBlue-Registrar-Office` |
| Networking | `form-Networking` | `btnSubmitBlue-Networking` |
| Directorate of Administration | `form-Directorate-of-Administration` | `btnSubmitBlue-Directorate-of-Administration` |
| Transmission | `form-Transmission` | `btnSubmitBlue-Transmission` |

### Ticket Form Fields
- **Query/Complaint** — Dropdown to select issue type
- **Comments** — Text area for detailed description
- **Attachment** — File upload for supporting documents

### Department of Computer Science Sub-Categories
- Final Project/Thesis/Internship
- General Queries
- For MSCS Courses Add or Drop requests

### Key Divs
- `div#wrapper` — Main container
- `div#content` — Content area
- `div#topContainerLogo` — Header logo
- `div#topAfterHeaderID` — Navigation bar
- `div#main` — Main content with accordion forms
- `div#dialog-{CATEGORY}` — Modal dialog per category
- `div#accordion-{CATEGORY}` — Accordion container per category
- `div#form-{CATEGORY}` — Form container per category

### Support System Workflow
1. **Select Category** — Choose the relevant department/category
2. **Fill Form** — Select query type, add comments, attach files if needed
3. **Submit Ticket** — Click submit to create ticket
4. **Track Tickets** — View "My Tickets" to check status of submitted tickets
5. **Receive Response** — Department responds via the support system

---

## Technical Notes

- VU LMS uses **ASP.NET WebForms** with `__doPostBack` for navigation
- All internal navigation uses JavaScript postbacks, not direct URLs
- External links (Mail, Contact, Help) use direct URLs
- Student ID format: `<XX000000000>` (2 letters + 9 digits, e.g., BC240404771)
- Course codes: `CSxxx`, `MCMxxx`, `ENGxxx`, `MTHxxx`, etc.
- Each course has its own directory: `/Courses/{CODE}/`
- Support System is a separate ticketing platform with its own login/session
- Support System allows: creating tickets, attaching files, tracking status, department routing
- Student data (ID, name, CNIC, phone, email, DOB, admission date) is CONFIDENTIAL and must not be shared