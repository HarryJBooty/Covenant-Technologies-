# 📸 UI Examples & Screenshots

## Main Menu

```
╔══════════════════════════════════════════════╗
║  🎮 Halo Group Management System             ║
╚══════════════════════════════════════════════╝

Welcome, @User!

Select an option below to get started:

📋 Officer Actions
• Log Event
• Report Duel Results

⚔️ Player Actions
• Challenge Player
• View Progress
• Start Quiz (Minor I only)

❓ Need Help?
Click the Help button for detailed command information.

┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ 📋 Log Event │ │ ⚔️ Report   │ │ ⚔️ Challenge │
└──────────────┘ └──────────────┘ └──────────────┘
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ 📊 Progress  │ │ 📝 Quiz     │ │ ❓ Help      │
└──────────────┘ └──────────────┘ └──────────────┘

Covenant Technologies • Halo Group Bot
```

## Event Logging Flow

### Step 1: Event Type Selection
```
╔══════════════════════════════════════════════╗
║  📋 Log Event                                 ║
╚══════════════════════════════════════════════╝

Select the type of event you want to log:

┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ ⚔️ Raid  │ │ 🛡️ Defense│ │ 🎯 Scrim │ │ 🏋️ Training│
└──────────┘ └──────────┘ └──────────┘ └──────────┘
┌──────────┐ ┌──────────┐ ┌──────────┐
│ 🎮 Gamenight │ 📢 Recruitment│ 📝 Other│
└──────────┘ └──────────┘ └──────────┘
```

### Step 2: Co-Host Selection
```
╔══════════════════════════════════════════════╗
║  👥 Select Co-Host                           ║
╚══════════════════════════════════════════════╝

Event Type: Raid

Click below to select a co-host, or choose 'No Co-Host':

┌─────────────────────────────────────┐
│ 🔽 Select co-host...               │
└─────────────────────────────────────┘
┌──────────────┐
│ No Co-Host   │
└──────────────┘
```

### Step 3: Attendee Selection
```
╔══════════════════════════════════════════════╗
║  👥 Select Attendees                         ║
╚══════════════════════════════════════════════╝

Event Type: Raid
Co-Host: @CoHost

Select all attendees from the dropdown, then click 'Finish':

┌─────────────────────────────────────┐
│ 🔽 Select attendees...             │
│    (you can select multiple times)  │
└─────────────────────────────────────┘
┌──────────────────────┐
│ ✅ Finish & Log Event│
└──────────────────────┘
```

### Step 4: Confirmation
```
╔══════════════════════════════════════════════╗
║  ✅ Event Logged Successfully                ║
╚══════════════════════════════════════════════╝

Event ID: 42
Type: Raid
Host: @Officer
Co-Host: @CoHost
Attendees (15): @Player1, @Player2, @Player3, @Player4, 
@Player5, @Player6, @Player7, @Player8, @Player9, 
@Player10 and 5 more

Covenant Technologies • Halo Group Bot
```

## Challenge Flow

### Challenge Sent
```
╔══════════════════════════════════════════════╗
║  ⚔️ Duel Challenge!                          ║
╚══════════════════════════════════════════════╝

@Opponent, you have been challenged to a duel by @Challenger!

Respond with:
• yes or accept to accept the challenge
• no or decline to decline

⏱️ You have 60 seconds to respond...

Covenant Technologies • Halo Group Bot
```

### Challenge Accepted
```
╔══════════════════════════════════════════════╗
║  ✅ Challenge Accepted!                      ║
╚══════════════════════════════════════════════╝

@Opponent has accepted the duel!

📨 Both players will receive a DM with the duel link.

Covenant Technologies • Halo Group Bot
```

### DM to Participants
```
╔══════════════════════════════════════════════╗
║  ⚔️ Duel Information                         ║
╚══════════════════════════════════════════════╝

Match: @Challenger vs @Opponent

Duel Link: https://example.com/your-duel-link

Good luck! May the best player win! 🎮

📋 After the Duel
An officer will use /report_duel to log the results.

Covenant Technologies • Halo Group Bot
```

## Progress Display

```
╔══════════════════════════════════════════════╗
║  📊 Progress Report: PlayerName              ║
╚══════════════════════════════════════════════╝

Your current stats and progress towards next rank:

🎯 Overall Completion
60% (3/4 requirements met)
[█████████──────] 

✅ Events Attended
7/7 events
[████████████]

⏳ Warfare Events
2/3 raids/defenses/scrims
[████████────]

✅ Training Events
2/2 trainings
[████████████]

✅ Duels Won
2/2 duels
[████████████]

🎯 Events Hosted
Total hosted: 5
Warfare hosted: 3

📝 Quiz Status
✅ Passed

Covenant Technologies • Keep up the great work!
```

## Quiz Flow

### Welcome Message
```
╔══════════════════════════════════════════════╗
║  📝 Minor I → Major III Quiz                 ║
╚══════════════════════════════════════════════╝

Welcome to the rank-up quiz!

Instructions:
• You will be asked 5 questions
• Type your answer and confirm it
• You can re-answer before confirming
• Your answers will be reviewed by staff

Ready? Let's begin!

Covenant Technologies • Halo Group Bot
```

### Question Display
```
╔══════════════════════════════════════════════╗
║  Question 1/5                                 ║
╚══════════════════════════════════════════════╝

What is the primary mission of the Covenant?

Question 1 of 5 • Type your answer below
```

### Answer Confirmation
```
╔══════════════════════════════════════════════╗
║  Confirm Your Answer                          ║
╚══════════════════════════════════════════════╝

Your answer:
```
To unite all species under the Great Journey
```

React with ✅ to confirm or ❌ to re-answer this question.

✅ ❌
```

### Quiz Completion
```
╔══════════════════════════════════════════════╗
║  🎉 Quiz Complete!                           ║
╚══════════════════════════════════════════════╝

Your quiz has been submitted for review by staff.

You will receive a DM notification once your quiz has been reviewed.

Thank you for your patience!

Covenant Technologies • Halo Group Bot
```

### Review Submission (Staff View)
```
╔══════════════════════════════════════════════╗
║  📝 Quiz Submission                          ║
╚══════════════════════════════════════════════╝

@here New quiz submission for review!

Candidate: @Player (PlayerName)
Rank Path: Minor I ➜ Major III
Submitted: 2 minutes ago

📌 Question 1
What is the primary mission of the Covenant?

💬 Answer
```
To unite all species under the Great Journey
```

📌 Question 2
...

✅ ❌  (React to approve/deny)

User ID: 123456789
Covenant Technologies • Halo Group Bot
```

### Pass Notification (DM)
```
╔══════════════════════════════════════════════╗
║  🎉 Quiz Passed!                             ║
╚══════════════════════════════════════════════╝

Congratulations! Your quiz has been reviewed and PASSED!

Reviewed by: @Reviewer

You are one step closer to your next rank! 🚀

Covenant Technologies • Halo Group Bot
```

## Duel Result Reporting

### Command Usage
```
╔══════════════════════════════════════════════╗
║  ✅ Duel Result Recorded                     ║
╚══════════════════════════════════════════════╝

Winner: @Winner 🏆
Loser: @Loser

Recorded by: @Officer

Covenant Technologies • Halo Group Bot
```

### Winner Notification (DM)
```
╔══════════════════════════════════════════════╗
║  🏆 Duel Victory!                            ║
╚══════════════════════════════════════════════╝

Congratulations! Your duel victory has been recorded.

Opponent: @Loser
Recorded by: @Officer

Covenant Technologies • Halo Group Bot
```

## Help Display

```
╔══════════════════════════════════════════════╗
║  ❓ Help & Commands                          ║
╚══════════════════════════════════════════════╝

Here's everything you can do with this bot:

📋 Log Event (Officers Only)
Log raids, defenses, scrims, trainings, and more. Select event type, 
co-host, and attendees through an interactive menu.

⚔️ Challenge Player
Challenge another player to a duel.
Command: /challenge @opponent

⚔️ Report Duel (Officers Only)
Report duel results after completion.
Command: /report_duel @winner @loser

📊 View Progress
Check your stats, including events attended, duels won, and quiz status.
Shows progress bars for rank requirements.

📝 Quiz (Minor I Only)
Start the rank-up quiz. Questions will be sent via DM, and your answers 
will be reviewed by staff.

🏠 Main Menu
Use /menu or !menu to open this interactive menu anytime!

Covenant Technologies • Halo Group Bot
```

## Error Messages

### Permission Denied
```
╔══════════════════════════════════════════════╗
║  🔒 Permission Denied                        ║
╚══════════════════════════════════════════════╝

Only officers can log events.

Covenant Technologies • Halo Group Bot
```

### Invalid Input
```
╔══════════════════════════════════════════════╗
║  Invalid Target                               ║
╚══════════════════════════════════════════════╝

You cannot challenge yourself!

Covenant Technologies • Halo Group Bot
```

### Timeout
```
╔══════════════════════════════════════════════╗
║  ⏱️ Challenge Expired                        ║
╚══════════════════════════════════════════════╝

@Opponent did not respond in time.

The duel challenge has been cancelled.

Covenant Technologies • Halo Group Bot
```

---

## 🎨 Color Scheme

- **Primary (Purple)**: Main actions, titles, general information
- **Success (Green)**: Confirmations, completed items, victories
- **Error (Red)**: Errors, failures, denials
- **Info (Blue)**: Help, information, neutral messages
- **Warning (Orange)**: Pending actions, awaiting response, retries

## 📱 Interactive Elements

- **Buttons**: Touch-friendly, color-coded, with clear labels
- **Dropdowns**: Multi-select support, clear placeholders
- **Reactions**: Quick yes/no confirmations
- **Embeds**: Rich formatting with fields, thumbnails, footers

## ✨ Visual Features

- User avatars in relevant embeds
- Emoji indicators throughout
- Progress bars with fill indicators
- Timestamps on all messages
- Consistent footer branding
- Field organization for readability
- Color coding for quick recognition

---

**Every interaction is now a polished, professional experience!** 🌟
