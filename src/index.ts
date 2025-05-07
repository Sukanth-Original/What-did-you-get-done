// index.ts but for multiple users

import { TpaServer, TpaSession } from '@augmentos/sdk';
import * as fs from 'fs';
import * as path from 'path';

const PACKAGE_NAME = "# insert ur packaga name";
const PORT = 80;
const API_KEY = 'insert your api key';


// Configurable settings
const WORK_START_HOUR = 0;       // 12 AM
const WORK_END_HOUR = 24;        // 12 PM
const REMINDER_INTERVAL_MIN = 15; // every 2 minutes
const INACTIVITY_TIMEOUT = 60000; // 1 minute
const HOTWORD = "Elon";

// File path for session tracking
const SESSION_FILE_PATH = path.join(__dirname, 'session_data.json');
let activeSessionsByUser: Record<string, number> = {}; // Track active session number per user
let activeSessions: Record<string, any> = {}; // Track active sessions and their states (key format: "userId:sessionNumber")

// Initialize session data if file doesn't exist
if (!fs.existsSync(SESSION_FILE_PATH)) {
  fs.writeFileSync(SESSION_FILE_PATH, JSON.stringify({}, null, 2));
}

// Load existing session data to memory
try {
  const fileContent = fs.readFileSync(SESSION_FILE_PATH, 'utf-8');
  activeSessionsByUser = JSON.parse(fileContent);
  console.log('Loaded session data:', activeSessionsByUser);
} catch (e) {
  console.error('Error loading session data, starting fresh:', e);
}

function getNextSessionNumber(userId: string): number {
  try {
    // Get the next session number for this user
    const currentSessionNumber = activeSessionsByUser[userId] || 0;
    const nextSessionNumber = currentSessionNumber + 1;
    
    // Update the session data and write back to file
    activeSessionsByUser[userId] = nextSessionNumber;
    fs.writeFileSync(SESSION_FILE_PATH, JSON.stringify(activeSessionsByUser, null, 2));
    
    console.log(`Assigned session ${nextSessionNumber} to user ${userId}`);
    return nextSessionNumber;
  } catch (error) {
    console.error('Error handling session file:', error);
    return 1;
  }
}

function terminateEarlierSessions(userId: string, sessionNumber: number) {
  // Find session keys that belong to this user with lower session numbers
  Object.keys(activeSessions).forEach((key) => {
    // Key format is "userId:sessionNumber"
    const [keyUserId, keySessionStr] = key.split(':');
    const keySessionNum = parseInt(keySessionStr, 10);
    
    if (keyUserId === userId && keySessionNum < sessionNumber) {
      console.log(`Terminating session ${keySessionNum} for user ${userId}...`);
      const sessionState = activeSessions[key];
      if (sessionState) {
        if (sessionState.inactivityTimer) clearTimeout(sessionState.inactivityTimer);
        if (sessionState.reminderTimer) clearTimeout(sessionState.reminderTimer);
        sessionState.cancelled = true; // 🚨 Mark as cancelled
      }
    }
  });
}

class MyAugmentOSApp extends TpaServer {
  protected async onSession(session: TpaSession, sessionId: string, userId: string): Promise<void> {
    const sessionNumber = getNextSessionNumber(userId);
    console.log(`Starting session ${sessionNumber} for user ${userId}`);

    // Always process the newest session for a user
    // (We're already incrementing in getNextSessionNumber so this will always be the latest)
    console.log(`New session ${sessionNumber} started for user ${userId}, terminating previous sessions.`);
    terminateEarlierSessions(userId, sessionNumber);

    const sessionKey = `${userId}:${sessionNumber}`;
    
    let isListening = false;
    let manualListening = false;
    let reminderListening = false;
    let inactivityTimer: NodeJS.Timeout | null = null;
    let reminderTimer: NodeJS.Timeout | null = null;
    let lastActivityTimestamp = Date.now();
    let cancelled = false;

    activeSessions[sessionKey] = { 
      inactivityTimer, 
      reminderTimer, 
      isListening, 
      manualListening, 
      reminderListening, 
      lastActivityTimestamp, 
      cancelled 
    };

    const logAndShow = (msg: string) => {
      console.log(`User ${userId} Session ${sessionNumber}: ${msg}`);
      session.layouts.showTextWall(msg);
    };

    function isWithinWorkingHours(): boolean {
      const hour = new Date().getHours();
      return hour >= WORK_START_HOUR && hour < WORK_END_HOUR;
    }

    function scheduleNextReminder() {
      const sessionState = activeSessions[sessionKey];
      if (!sessionState || sessionState.cancelled) {
        console.log(`Session ${sessionNumber} for user ${userId} cancelled, not scheduling reminders.`);
        return;
      }
      if (reminderTimer) clearTimeout(reminderTimer);

      if (!isWithinWorkingHours()) {
        const now = new Date();
        const start = new Date(now);
        start.setHours(WORK_START_HOUR, 0, 0, 0);
        if (now >= start) start.setDate(start.getDate() + 1);
        const ms = start.getTime() - now.getTime();
        reminderTimer = setTimeout(scheduleNextReminder, ms);
        console.log(`User ${userId}: Scheduled next reminder at work start in ${ms}ms`);
        return;
      }

      const now = new Date();
      const mins = now.getMinutes();
      const next = Math.ceil(mins / REMINDER_INTERVAL_MIN) * REMINDER_INTERVAL_MIN;
      const nextReminder = new Date(now);
      nextReminder.setMinutes(next, 0, 0);
      if (nextReminder <= now) nextReminder.setMinutes(next + REMINDER_INTERVAL_MIN, 0, 0);
      const ms = nextReminder.getTime() - now.getTime();
      console.log(`User ${userId}: Next reminder in ${ms}ms at ${nextReminder.toLocaleTimeString()}`);

      reminderTimer = setTimeout(() => {
        const sessionState = activeSessions[sessionKey];
        if (!sessionState || sessionState.cancelled) {
          console.log(`Session ${sessionNumber} for user ${userId} cancelled, aborting reminder.`);
          return;
        }
        if (!isListening) {
          checkAndTriggerReminder();
        } else {
          console.log(`User ${userId}: Skipping reminder: active conversation in progress`);
        }
        scheduleNextReminder();
      }, ms);
    }

    function checkAndTriggerReminder() {
      const sessionState = activeSessions[sessionKey];
      if (!sessionState || sessionState.cancelled) return;
      if (!isWithinWorkingHours()) return;
      if (isListening) {
        console.log(`User ${userId}: Skipping reminder: active conversation in progress`);
        return;
      }
      triggerReminder();
    }

    function triggerReminder() {
      const sessionState = activeSessions[sessionKey];
      if (!sessionState || sessionState.cancelled) return;
      if (isListening) {
        console.log(`User ${userId}: Already listening, skip setting reminder.`);
        return;
      }
      const timeString = new Date().toLocaleTimeString();
      const prompt = `What did you get done in the past ${REMINDER_INTERVAL_MIN} minutes?`;
      logAndShow(prompt + ` (${timeString})`);

      reminderListening = true;
      isListening = true;
      resetInactivityTimer();
    }

    function recordActivity() {
      const sessionState = activeSessions[sessionKey];
      if (!sessionState || sessionState.cancelled) return;
      console.log(`User ${userId}: Activity recorded at`, new Date().toLocaleTimeString());
      lastActivityTimestamp = Date.now();
      resetInactivityTimer();
    }

    function resetInactivityTimer() {
      const sessionState = activeSessions[sessionKey];
      if (!sessionState || sessionState.cancelled) return;
      if (inactivityTimer) clearTimeout(inactivityTimer);
      inactivityTimer = setTimeout(() => {
        const elapsed = Date.now() - lastActivityTimestamp;
        if (elapsed >= INACTIVITY_TIMEOUT && isListening) {
          console.log(`User ${userId}: Inactivity timeout for 60 seconds, ending conversation`);
          isListening = false;
          manualListening = false;
          reminderListening = false;
          logAndShow(`Say "${HOTWORD}" when you wanna talk.`);
        }
      }, INACTIVITY_TIMEOUT);
    }

    logAndShow(`Say "${HOTWORD}" when you wanna talk.`);
    scheduleNextReminder();

    const unsubscribe = session.events.onTranscription(async (data) => {
      const sessionState = activeSessions[sessionKey];
      if (!sessionState || sessionState.cancelled) {
        console.log(`Session ${sessionNumber} for user ${userId} cancelled, ignoring transcription.`);
        return;
      }
      recordActivity();
      if (!data.isFinal) {
        if (isListening) session.layouts.showTextWall(data.text);
        return;
      }

      const text = data.text.trim();
      console.log(`[FINAL] User ${userId}: ${text}`);
      recordActivity();

      if (reminderListening) {
        reminderListening = false;
        await processWithLLM(text, `Here is what the user has been doing for the past ${REMINDER_INTERVAL_MIN} minutes: ${text}`);
        return;
      }

      if (!isListening && text.toLowerCase().includes(HOTWORD.toLowerCase())) {
        isListening = true;
        manualListening = true;
        logAndShow(`${HOTWORD} here, go on?`);
        return;
      }

      if (isListening) {
        session.layouts.showTextWall(text);
        await processWithLLM(text, text);
      }
    });

    async function processWithLLM(userText: string, prompt: string) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 100000);
        const response = await fetch('http://backend:8000/generate', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ prompt, user_id: userId }),
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        if (!response.ok) throw new Error('LLM request failed');
        const { response: botReply } = await response.json();
        session.layouts.showTextWall(`${userText}\n\n${HOTWORD}: ${botReply}`);
      } catch (e) {
        console.error(`User ${userId} LLM Error:`, e);
        session.layouts.showTextWall("Say that again? pls...");
      }
    }

    await new Promise<void>(resolve => {
      session.events.onDisconnected(() => {
        const sessionState = activeSessions[sessionKey];
        if (sessionState) {
          if (sessionState.inactivityTimer) clearTimeout(sessionState.inactivityTimer);
          if (sessionState.reminderTimer) clearTimeout(sessionState.reminderTimer);
          sessionState.cancelled = true;
        }
        unsubscribe();
        delete activeSessions[sessionKey];
        resolve();
      });
    });
  }
}

const server = new MyAugmentOSApp({ packageName: PACKAGE_NAME, apiKey: API_KEY, port: PORT });
server.start().catch(err => console.error('Failed to start server:', err));