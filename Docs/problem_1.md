# Objective 1 — Build a repeatable daily study habit

I would concentrate the first adoption improvements on one journey:

**Home → today’s study task → focus → record progress → see the result**

This builds on existing features and gives students a practical reason to return. Before setting improvement targets, I would clarify the reporting period, denominator and treatment of timer time behind the current 2.15-minute average and the 30-minute goal.

## 1. Make the first focus session clear and achievable

The brief reports that 11 students opened Focus, but only five use it regularly. During my walkthrough, switching to another app ended my session. The shortest available session is 25 minutes, and the Give Up confirmation warns of a 50-coin penalty.

An unexpected failure during the first attempt may discourage another attempt.

Before Start, I would explain the commitment, permitted interruptions and consequences. The intended experience keeps students within Alcovia while allowing calls from approved parent numbers. The engineer would validate this behaviour on supported devices, including calls and screen locks.

The first release would improve only the guidance before Focus starts, based on verified behaviour. A ten-minute introductory session with an appropriately sized reward would be a later experiment, subject to the pilot findings. Where blocking cannot be enforced, I would evaluate a 60-second return window with a reminder, explicitly treating this as a fallback. Duration, blocking and reward redesign are outside the first release.

Measure first-session completion, abandonment reasons and another session within seven days. **Reported adoption baseline: five regular Focus users.** Completion and return-rate baselines would be established separately.

## 2. Make the daily target actionable

The streak screen ties maintaining a streak to the daily syllabus target, but the Daily Velocity card does not open the work needed to reach it. The brief reports only one Streak user.

Students may struggle to connect the percentage target to their next action, weakening its usefulness as a daily prompt.

I would make the card open relevant work and explain what contributes to the target. Where the relationship is confirmed, show the remaining tasks alongside the percentage. Students should understand what to do, why it matters and how completion affects progress.

Measure whether students can explain the target, reach a relevant task and complete it. Track actual streak continuity separately from visits to the Streak feature. **Reported feature-usage baseline: one Streak user.**

## 3. Make recording progress part of finishing study

The brief reports ten students opening Syllabus across the 45-day review period, with one opening it this week. Study was used by two of the 13 students active this week. These different windows signal a concern; they do not establish a retention rate.

Study already provides a route from chapter work into Focus. Extra steps between finishing work and recording it may reduce progress logging and leave students unsure what they achieved.

I would test the current return journey and make progress confirmation a single step. For a session linked to a task, ask “How far did you get?” with Done, Partly and Not yet. Save the response and show the confirmed result on Home. Completing a timer alone should not mark academic work complete.

Measure task-linked sessions with progress saved, chapter tasks completed and repeat Study use. Before attributing inactivity to motivation, check that suitable subjects, tasks and goals are available.

## Execution and evaluation

Joining on 1 November, I would begin the scheduled work on 2 November. This follows the shared [Problem 3 workplan](problem-3-workplan.md) and [delivery workbook](delivery-workplan.xlsx), which reserve capacity for the GTM tracker and student dashboard alongside app adoption.

I would own student research, prioritization, participant availability and evaluation. The process/systems designer would check content readiness, current progress-reporting steps and unaided use. The full-stack engineer would verify measurement, test device behaviour and handle implementation and release.

| Window | App-adoption work and ownership |
| --- | --- |
| 2–3 November | I agree the outcome and scope and interview five students spanning regular, occasional and lapsed use. The designer agrees metric definitions and checks content readiness. The engineer confirms build access, the existing TestFlight/Android APK release routes and measurement. We establish the baseline and pilot acceptance criteria. |
| 4–6 November | The engineer builds the pre-start Focus guidance and measurement and identifies the candidate version. The build estimate is two engineer days; device testing, approval, distribution and installation are separate. |
| 9–13 November | The engineer completes interruption-path testing by 10 November and targets packaging/submission for 11 November; approval is not promised by that date. The designer targets the unaided-use check for 13 November. I confirm post-Diwali availability. This is not the main student-engagement test week. |
| 16–20 November | Target pilot start: 16 November. Before observation starts, the engineer verifies required approval, installed versions and reporting, and the designer completes the usability check. I observe completion, abandonment and help required without coaching, recording each student's actual start and expected study days. A material failure stops further rollout. |
| 23–27 November | I review each student's full seven-day repeat-use window with the designer, reporting counts, denominators, absences and missing follow-up. The target follow-up review is 27 November. |
| 30 November | We review outcomes and operating effort and decide Keep, Improve or Stop. If inconclusive, we allow one further week with a specific question; otherwise we change the test or stop. Later experiments and Daily Velocity/progress-recording changes are prioritized from the findings, without committing them to this month's build capacity. |

Release, usability and installation checks must pass before the pilot. If they are delayed, the pilot and follow-up dates move; a late pilot is not declared successful before its full observation window ends.

I would compare equivalent periods and review individual outcomes alongside counts and percentages. The 30-minute goal would remain visible alongside completed study actions and repeat use, with focus, game and idle time distinguished.

