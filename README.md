# Covenant Technologies - Halo Group Bot

A comprehensive Discord bot for managing Halo group activities, events, duels, quizzes, and member progress with an **enhanced interactive UI system**.

## ✨ Features

### 🎮 Enhanced Interactive UI
- **Main Menu System**: Button-based navigation for all bot features
- **Visual Event Logging**: Select event types, co-hosts, and attendees with interactive dropdowns
- **Rich Embeds**: Beautiful, styled messages with consistent branding
- **Progress Tracking**: Visual progress bars showing rank advancement
- **Real-time Notifications**: DM notifications for challenges, duels, and quiz results

### 📋 Core Features

#### For All Members
- **Challenge System**: Challenge other players to duels with accept/decline buttons
- **Progress Tracking**: View detailed stats including:
  - Events attended (raids, defenses, scrims, training)
  - Duels won
  - Events hosted
  - Quiz completion status
  - Visual progress bars for rank requirements
- **Quiz System**: Interactive quiz for Minor I members to rank up to Major III
  - Answer confirmation system
  - Staff review with reactions
  - Automatic notifications

#### For Officers
- **Event Logging**: Interactive system to log various event types:
  - Raids
  - Defenses
  - Scrims
  - Trainings
  - Gamenights
  - Recruitment events
  - Custom events
- **Duel Reporting**: Record duel results with winner/loser tracking
- **Quiz Review**: Approve/deny quiz submissions with ✅/❌ reactions

## 🚀 Quick Start

### Primary Command
```
!menu or ?menu
```
Opens the main interactive menu with buttons for all features!

### Available Commands

| Command | Description | Access |
|---------|-------------|--------|
| `!menu` | Open main interactive menu | Everyone |
| `!help` | Show detailed help information | Everyone |
| `!progress [@user]` | View progress and stats | Everyone |
| `!stats [@user]` | Alias for progress | Everyone |
| `!challenge @user` | Challenge someone to a duel | Everyone |
| `!quiz` | Start rank-up quiz | Minor I only |
| `!log_event` | Log an event (redirects to menu) | Officers |
| `!report_duel @winner @loser` | Report duel results | Officers |

## 🎨 UI Enhancements

### Main Menu
- Visual button interface
- Role-based feature access
- Persistent 5-minute timeout
- Thumbnail with user avatar

### Event Logging
1. **Event Type Selection**: Visual buttons for each event type with emoji indicators
2. **Co-Host Selection**: User select dropdown or "No Co-Host" button
3. **Attendee Selection**: Multi-select dropdown supporting up to 25 users at once
4. **Confirmation**: Rich embed showing all event details

### Challenge System
- Styled challenge notifications
- 60-second response timer
- Accept/Decline options
- DM notifications to both participants
- Result logging

### Progress Display
- Overall completion percentage
- Individual progress bars for each requirement
- Check marks (✅) for completed requirements
- Clock icons (⏳) for pending requirements
- Color-coded embeds

### Quiz System
- Welcome message with instructions
- Question-by-question progression
- Answer confirmation with reactions
- Progress indicators between questions
- Beautifully formatted review submissions
- Staff notification system
- Result DM notifications

## 🎯 Default Requirements

Configure in `main.py`:
```python
DEFAULT_REQUIREMENTS = {
    "events": 7,       # Total events to attend
    "warfare": 3,      # Warfare events (raids/defenses/scrims)
    "training": 2,     # Training sessions
    "duels": 2,        # Duels to win
}
```

## 🎨 UI Customization

The bot uses a centralized `UIStyle` class for consistent theming:
- **Primary Color**: Purple (138, 43, 226)
- **Success Color**: Green
- **Error Color**: Red
- **Info Color**: Blue
- **Warning Color**: Orange

All embeds include:
- Consistent footer: "Covenant Technologies • Halo Group Bot"
- Timestamps
- Emoji indicators
- User avatars where appropriate

## 📊 Database Schema

### Tables
- **users**: Discord user tracking with quiz status
- **events**: Event records with type, host, and co-host
- **event_attendance**: Links users to events they attended
- **duels**: Duel results tracking

## 🔧 Configuration

Edit the config section in `main.py`:

```python
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OFFICER_ROLE_IDS = [123456789]  # Your officer role IDs
MINOR_I_ROLE_ID = 123456789     # Minor I role ID
QUIZ_REVIEWER_ROLE_IDS = [123456789]  # Quiz reviewer role IDs
QUIZ_REVIEW_CHANNEL_ID = 123456789    # Review channel ID
```

## 🌟 UI Features Summary

✅ Button-based navigation
✅ Interactive dropdown menus
✅ Rich embed styling
✅ Progress bars and visual indicators
✅ Role-based access control
✅ Ephemeral messages for privacy
✅ DM notifications
✅ Reaction-based confirmations
✅ Loading states
✅ Error handling with styled messages
✅ Consistent branding throughout

## 📝 Development

### Requirements
- Python 3.8+
- discord.py 2.0+
- asyncpg
- PostgreSQL database

### Installation
```bash
pip install -r requirements.txt
```

### Running
```bash
python main.py
```

## 🤝 Support

For issues or feature requests, contact the Covenant Technologies development team.

---

**Covenant Technologies** • Powering the Halo Group experience with cutting-edge technology 
