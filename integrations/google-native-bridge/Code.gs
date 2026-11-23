/**
 * Postgrad Study Engine — Reusable Google-Native Bridge (Google Apps Script V8)
 *
 * Architecture:
 *   Gemini App / Scheduled Actions (Google AI Pro native Drive + Gmail connectors)
 *     <--> Google Drive (Postgrad-Cloud/) + Gmail Drafts ([POSTGRAD-INBOX] / [POSTGRAD-REVIEW])
 *     <--> Google Apps Script V8 (this single file, 5-minute time-driven trigger)
 *     ---> GitHub REST API (<YOUR_GITHUB_OWNER>/<YOUR_PRIVATE_VAULT>, single-repo Fine-Grained PAT)
 *     ---> GitHub Actions (Process mobile inbox -> locked Core v0.5.1 -> outbox receipts)
 *
 * Security & Reliability Guarantees:
 *   - Zero Gemini Developer API calls; zero GCP billing; zero Service Account; zero Web App doPost.
 *   - LockService.getScriptLock() prevents overlapping executions.
 *   - Downlink uses Drive v3 Drive.Files.update() in-place overwrite preserving File IDs (fast for
 *     large docs; DocumentApp fallback only when Drive Advanced Service is unavailable), and skips
 *     unchanged docs via GitHub HEAD + blob SHA fingerprints.
 *   - Uplink [POSTGRAD-INBOX] strictly allows ONLY inbox/<request_id>.json, validates locally
 *     against locked Core v0.5.1 schema, preserves legal Chinese quotes inside strings while
 *     rejecting structural curly quotes, enforces byte limits, checks GET before PUT (identical ->
 *     idempotent skip; conflict -> reject without overwrite), and short-polls outbox/<request_id>.json.
 *   - Uplink [POSTGRAD-REVIEW] strictly allows ONLY atomic two-file updates to
 *     analysis/daily/YYYY-MM-DD.md + analysis/learner_context.md with frontmatter & non-regression
 *     checks (never touches events/, records/, inbox/, outbox/, state/, config/, or code).
 */

/* ============================================================================
 * Constants & Defaults
 * ============================================================================ */

var BRIDGE_VERSION = '1.0.0';

var DEFAULT_CONFIG = {
  GITHUB_OWNER: 'YOUR_GITHUB_USERNAME',
  GITHUB_REPO: 'YOUR_PRIVATE_VAULT_REPO',
  GITHUB_BRANCH: 'main',
  CLOUD_FOLDER_NAME: 'Postgrad-Cloud',
  INBOX_FOLDER_NAME: 'Postgrad-Inbox',
  PROCESSED_FOLDER_NAME: 'Postgrad-Processed',
  REJECTED_FOLDER_NAME: 'Postgrad-Rejected',
  DOC_NAME_PROTOCOLS: 'Postgrad-1-协议与学科说明',
  DOC_NAME_STATE: 'Postgrad-2-学习画像与核心状态',
  DOC_NAME_LEDGERS: 'Postgrad-3-学习账本原始记录',
  DOC_NAME_SYNCLOG: 'Postgrad-4-同步日志与回执',
  DOC_NAME_QUEUE: 'Postgrad-Inbox-Queue',
  INBOX_SUBJECT_PREFIX: '[POSTGRAD-INBOX]',
  REVIEW_SUBJECT_PREFIX: '[POSTGRAD-REVIEW]',
  REJECTED_SUBJECT_PREFIX: '[POSTGRAD-REJECTED]',
  GMAIL_LABEL_PROCESSED: 'Postgrad-Processed',
  GMAIL_LABEL_REJECTED: 'Postgrad-Rejected',
  MAX_INBOX_BYTES: 65536,
  MAX_REVIEW_REPORT_BYTES: 65536,
  MAX_REVIEW_CONTEXT_BYTES: 32768,
  OUTBOX_POLL_INITIAL_MS: 6000,
  OUTBOX_POLL_INTERVAL_MS: 5000,
  OUTBOX_POLL_MAX_MS: 40000,
  LOCK_WAIT_MS: 25000,
  ALLOW_DAILY_REVIEW_PUBLISH: true,
  MAX_SYNC_LOG_ENTRIES: 35,
  MAX_RECENT_RECEIPTS: 20,
  LATEST_OUTBOX_IN_STATE_DOC: 15
};

var PROTOCOL_DOC_PATHS = [
  'engine.lock.json',
  'MOBILE_STUDY.md',
  'learner_profile.md',
  'POSTGRAD_STATUS.md',
  'docs/DAILY_REVIEW.md',
  'docs/STUDY_SESSION_PROTOCOL.md',
  'skills/vault-study-tutor/SKILL.md',
  'subjects/math.md',
  'subjects/english.md',
  'subjects/materials.md',
  'subjects/physical_chemistry.md',
  'subjects/politics.md'
];

var STATE_STATIC_PATHS = [
  'analysis/learner_context.md',
  'exports/latest.md',
  'exports/study_records.json',
  'state/knowledge_units.json'
];

var LEDGER_DOC_PATHS = [
  'records/study_records.jsonl',
  'events/learning_events.jsonl'
];

var QUEUE_DOC_HEADER = [
  '# Postgrad-Inbox-Queue（备用上行队列）',
  '# 首选通道仍是 Gmail 草稿（主题前缀 [POSTGRAD-INBOX]）。',
  '# 如使用本队列文档，请粘贴完整 JSON 信封；多条记录之间用单独一行 ===POSTGRAD-ITEM=== 分隔。',
  '# 桥接脚本先检查文档更新时间，未修改不打开文档；处理成功的条目会自动清除，失败条目会附带报错保留。',
  ''
].join('\n');

/* ============================================================================
 * Core v0.5.1 Contract Constants (aligned with postgrad-study-engine/scripts/contracts.py)
 * ============================================================================ */

var REQUEST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
var INBOX_TARGET_RE = /^inbox\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\.json$/;
var REVIEW_TARGET_RE = /^analysis\/daily\/(\d{4}-\d{2}-\d{2})\.md$/;
var REVIEW_REQUEST_ID_RE = /^review-\d{4}-\d{2}-\d{2}(?:-[A-Za-z0-9._-]+)?$/;
var UNIT_ID_RE = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/;
var EVENT_ID_RE = /^\S+$/;
var SHA256_RE = /^[a-fA-F0-9]{64}$/;
var ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
var ISO_DATETIME_TZ_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|([+-])(\d{2}):(\d{2}))$/;
var UNSAFE_JSONL_SEPARATORS_RE = /[\u2028\u2029\u0085]/;
var STRUCTURAL_CURLY_QUOTES = {
  '\u201C': true, // “
  '\u201D': true, // ”
  '\u2018': true, // ‘
  '\u2019': true, // ’
  '\u300C': true, // 「
  '\u300D': true  // 」
};

var CORE_OPERATIONS = {
  record_attempt: true,
  record_diagnosis: true,
  register_unit: true,
  save_session_result: true,
  request_schedule: true,
  update_source_reference: true,
  record_contest_baseline: true,
  project_change_request: true,
  save_study_record: true
};

var SUBJECTS = {
  math: true,
  english: true,
  materials: true,
  politics: true,
  physical_chemistry: true,
  math_contest: true
};

var EVENT_TYPES = { attempt: true, diagnosis: true };
var ACTIVITIES = {
  learn: true,
  recall: true,
  solve: true,
  review: true,
  timed_practice: true,
  explain: true,
  variant: true
};
var RESULTS = { correct: true, incorrect: true, partial: true, unanswered: true };
var ANSWER_MODES = { independent: true, guess: true, uncertain: true, recalled: true, assisted: true };
var PROCESS_CHECKS = { clean: true, suspicious: true, not_available: true };
var DIAGNOSIS_STATUSES = { hypothesized: true, confirmed: true, rejected: true, unresolved: true };
var DIAGNOSIS_GENERATORS = { codex: true, learner: true, joint: true };
var CONFIRMATION_METHODS = {
  draft_check: true,
  learner_recall: true,
  redo: true,
  variant: true,
  delayed_review: true,
  not_confirmed: true
};
var VARIANT_LEVELS = { isomorphic: true, near_transfer: true, boundary: true, mixed_transfer: true };
var EVIDENCE_TARGETS = {
  comprehension: true,
  recall: true,
  independent: true,
  transfer: true,
  delayed: true,
  timed: true
};
var SOURCE_KINDS = { book: true, question: true, image: true, official_notice: true, other: true };
var TASK_TYPES = {
  correction: true,
  diagnostic: true,
  targeted_variant: true,
  review: true,
  practice: true,
  new_study: true,
  timed_practice: true
};
var FORBIDDEN_TRANSCRIPT_FIELDS = {
  transcript: true,
  transcripts: true,
  messages: true,
  conversation: true,
  chat_history: true,
  chat_transcript: true
};

/* ============================================================================
 * Public Entry Points (Apps Script Triggers & Manual Setup)
 * ============================================================================ */

/**
 * One-time bootstrap: verifies GITHUB_TOKEN, locates or creates Postgrad-Cloud/
 * folders and fixed Google Docs, caches IDs in ScriptProperties, installs the
 * 5-minute trigger for runBridgeCycle, and performs an initial downlink sync.
 */
function setupBridge() {
  return withScriptLock(function () {
    var cfg = loadConfig();
    requireGitHubToken(cfg);
    var resources = ensureDriveResources(cfg);
    installTrigger();
    var downResult = syncDownlinkInternal(cfg, resources, true);
    appendSyncLog(cfg, {
      ts: formatShanghaiNow(),
      action: 'setup',
      status: 'ok',
      detail: 'folder=' + resources.cloudFolderId + ', synced=' + downResult.updatedDocs.join(',')
    });
    refreshSyncLogDoc(cfg, resources);
    return {
      status: 'ok',
      bridge_version: BRIDGE_VERSION,
      resources: resources,
      downlink: downResult
    };
  });
}

/**
 * Idempotently installs a single 5-minute time-based trigger for runBridgeCycle.
 */
function installTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'runBridgeCycle') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger('runBridgeCycle').timeBased().everyMinutes(5).create();
  return { status: 'ok', handler: 'runBridgeCycle', interval_minutes: 5 };
}

/**
 * Main 5-minute scheduled bridge cycle:
 *   1. Uplink: Gmail drafts -> Sent Gmail -> Drive Postgrad-Inbox -> Drive Queue Doc
 *   2. Outbox polling for newly uploaded + previously pending inbox requests
 *   3. Downlink: GitHub main -> Postgrad-1 / Postgrad-2 / Postgrad-3 (only when SHA changed)
 *   4. Update Postgrad-4-同步日志与回执 if any event or receipt changed
 */
function runBridgeCycle() {
  return withScriptLock(function () {
    var cfg = loadConfig();
    requireGitHubToken(cfg);
    var resources = ensureDriveResources(cfg);

    var summary = {
      started_at: formatShanghaiNow(),
      uplink: {
        processed: 0,
        uploaded: 0,
        idempotent_skipped: 0,
        rejected: 0,
        transient_errors: 0,
        reviews_published: 0
      },
      outbox_resolved: [],
      downlink: { skipped: true, updatedDocs: [], headSha: null }
    };

    var syncLogDirty = false;
    var newlySubmittedIds = [];

    // 1a. Gmail Drafts (Primary channel)
    var draftStats = processGmailDrafts(cfg, summary, newlySubmittedIds);
    if (draftStats.changed) syncLogDirty = true;

    // 1b. Sent / Received Gmail Messages (Compatible channel)
    var msgStats = processGmailMessages(cfg, summary, newlySubmittedIds);
    if (msgStats.changed) syncLogDirty = true;

    // 1c. Drive Postgrad-Inbox/ folder (Compatible channel)
    var folderStats = processDriveInboxFolder(cfg, resources, summary, newlySubmittedIds);
    if (folderStats.changed) syncLogDirty = true;

    // 1d. Drive Postgrad-Inbox-Queue Doc (Compatible channel, fast-path getLastUpdated check)
    var queueStats = processDriveQueueDoc(cfg, resources, summary, newlySubmittedIds);
    if (queueStats.changed) syncLogDirty = true;

    // 2. Poll outbox receipts (newly uploaded + previously pending)
    var pollResult = pollOutboxReceipts(cfg, newlySubmittedIds);
    summary.outbox_resolved = pollResult.resolved;
    if (pollResult.changed) syncLogDirty = true;

    // 3. Downlink sync (GitHub main -> Drive fixed Docs, SHA-fingerprinted)
    var downResult = syncDownlinkInternal(cfg, resources, false);
    summary.downlink = downResult;
    if (downResult.updatedDocs.length > 0) {
      syncLogDirty = true;
      appendSyncLog(cfg, {
        ts: formatShanghaiNow(),
        action: 'downlink',
        status: 'ok',
        detail: 'head=' + shortSha(downResult.headSha) + ' updated=' + downResult.updatedDocs.join(',')
      });
    }

    // 4. Refresh Sync Log Doc only when something changed (or never initialized)
    if (syncLogDirty || !getProp('SYNCLOG_INITIALIZED')) {
      refreshSyncLogDoc(cfg, resources);
      setProp('SYNCLOG_INITIALIZED', 'true');
    }

    return summary;
  });
}

/**
 * Manual utility: force-refresh all 3 mirrored Docs from GitHub main right now.
 */
function forceSyncDownlink() {
  return withScriptLock(function () {
    var cfg = loadConfig();
    requireGitHubToken(cfg);
    var resources = ensureDriveResources(cfg);
    var downResult = syncDownlinkInternal(cfg, resources, true);
    appendSyncLog(cfg, {
      ts: formatShanghaiNow(),
      action: 'force_downlink',
      status: 'ok',
      detail: 'head=' + shortSha(downResult.headSha) + ' updated=' + downResult.updatedDocs.join(',')
    });
    refreshSyncLogDoc(cfg, resources);
    return downResult;
  });
}

/**
 * Manual utility: run only uplink + outbox polling.
 */
function syncUplinkOnly() {
  return withScriptLock(function () {
    var cfg = loadConfig();
    requireGitHubToken(cfg);
    var resources = ensureDriveResources(cfg);
    var summary = {
      started_at: formatShanghaiNow(),
      uplink: {
        processed: 0,
        uploaded: 0,
        idempotent_skipped: 0,
        rejected: 0,
        transient_errors: 0,
        reviews_published: 0
      },
      outbox_resolved: []
    };
    var newlySubmittedIds = [];
    processGmailDrafts(cfg, summary, newlySubmittedIds);
    processGmailMessages(cfg, summary, newlySubmittedIds);
    processDriveInboxFolder(cfg, resources, summary, newlySubmittedIds);
    processDriveQueueDoc(cfg, resources, summary, newlySubmittedIds);
    var pollResult = pollOutboxReceipts(cfg, newlySubmittedIds);
    summary.outbox_resolved = pollResult.resolved;
    refreshSyncLogDoc(cfg, resources);
    return summary;
  });
}

/* ============================================================================
 * Locking & Configuration Helpers
 * ============================================================================ */

function withScriptLock(fn) {
  var lock = LockService.getScriptLock();
  var waitMs = Number(getProp('LOCK_WAIT_MS')) || DEFAULT_CONFIG.LOCK_WAIT_MS;
  var acquired = lock.tryLock(waitMs);
  if (!acquired) {
    Logger.log('Postgrad bridge skipped: could not acquire ScriptLock within ' + waitMs + 'ms.');
    return { status: 'skipped_lock_busy' };
  }
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

function getProp(key) {
  return PropertiesService.getScriptProperties().getProperty(key);
}

function setProp(key, value) {
  PropertiesService.getScriptProperties().setProperty(key, String(value));
}

function loadConfig() {
  var props = PropertiesService.getScriptProperties().getProperties() || {};
  function pickStr(key, fallback) {
    return props[key] && String(props[key]).trim() ? String(props[key]).trim() : fallback;
  }
  function pickNum(key, fallback) {
    var v = Number(props[key]);
    return (isFinite(v) && v > 0) ? v : fallback;
  }
  function pickBool(key, fallback) {
    if (props[key] === undefined || props[key] === null || props[key] === '') return fallback;
    return String(props[key]).trim().toLowerCase() !== 'false';
  }
  return {
    githubToken: pickStr('GITHUB_TOKEN', ''),
    githubOwner: pickStr('GITHUB_OWNER', DEFAULT_CONFIG.GITHUB_OWNER),
    githubRepo: pickStr('GITHUB_REPO', DEFAULT_CONFIG.GITHUB_REPO),
    githubBranch: pickStr('GITHUB_BRANCH', DEFAULT_CONFIG.GITHUB_BRANCH),
    cloudFolderName: pickStr('CLOUD_FOLDER_NAME', DEFAULT_CONFIG.CLOUD_FOLDER_NAME),
    inboxFolderName: pickStr('INBOX_FOLDER_NAME', DEFAULT_CONFIG.INBOX_FOLDER_NAME),
    processedFolderName: pickStr('PROCESSED_FOLDER_NAME', DEFAULT_CONFIG.PROCESSED_FOLDER_NAME),
    rejectedFolderName: pickStr('REJECTED_FOLDER_NAME', DEFAULT_CONFIG.REJECTED_FOLDER_NAME),
    docNameProtocols: pickStr('DOC_NAME_PROTOCOLS', DEFAULT_CONFIG.DOC_NAME_PROTOCOLS),
    docNameState: pickStr('DOC_NAME_STATE', DEFAULT_CONFIG.DOC_NAME_STATE),
    docNameLedgers: pickStr('DOC_NAME_LEDGERS', DEFAULT_CONFIG.DOC_NAME_LEDGERS),
    docNameSyncLog: pickStr('DOC_NAME_SYNCLOG', DEFAULT_CONFIG.DOC_NAME_SYNCLOG),
    docNameQueue: pickStr('DOC_NAME_QUEUE', DEFAULT_CONFIG.DOC_NAME_QUEUE),
    inboxSubjectPrefix: DEFAULT_CONFIG.INBOX_SUBJECT_PREFIX,
    reviewSubjectPrefix: DEFAULT_CONFIG.REVIEW_SUBJECT_PREFIX,
    rejectedSubjectPrefix: DEFAULT_CONFIG.REJECTED_SUBJECT_PREFIX,
    gmailLabelProcessed: DEFAULT_CONFIG.GMAIL_LABEL_PROCESSED,
    gmailLabelRejected: DEFAULT_CONFIG.GMAIL_LABEL_REJECTED,
    maxInboxBytes: pickNum('MAX_INBOX_BYTES', DEFAULT_CONFIG.MAX_INBOX_BYTES),
    maxReviewReportBytes: pickNum('MAX_REVIEW_REPORT_BYTES', DEFAULT_CONFIG.MAX_REVIEW_REPORT_BYTES),
    maxReviewContextBytes: pickNum('MAX_REVIEW_CONTEXT_BYTES', DEFAULT_CONFIG.MAX_REVIEW_CONTEXT_BYTES),
    outboxPollInitialMs: pickNum('OUTBOX_POLL_INITIAL_MS', DEFAULT_CONFIG.OUTBOX_POLL_INITIAL_MS),
    outboxPollIntervalMs: pickNum('OUTBOX_POLL_INTERVAL_MS', DEFAULT_CONFIG.OUTBOX_POLL_INTERVAL_MS),
    outboxPollMaxMs: pickNum('OUTBOX_POLL_MAX_MS', DEFAULT_CONFIG.OUTBOX_POLL_MAX_MS),
    allowDailyReviewPublish: pickBool('ALLOW_DAILY_REVIEW_PUBLISH', DEFAULT_CONFIG.ALLOW_DAILY_REVIEW_PUBLISH)
  };
}

function requireGitHubToken(cfg) {
  if (!cfg.githubToken) {
    throw new Error('Missing ScriptProperty GITHUB_TOKEN. Configure a single-repo Fine-Grained PAT first.');
  }
  if (!cfg.githubOwner || cfg.githubOwner === 'YOUR_GITHUB_USERNAME' || !cfg.githubRepo || cfg.githubRepo === 'YOUR_PRIVATE_VAULT_REPO') {
    throw new Error('Set ScriptProperties GITHUB_OWNER and GITHUB_REPO to your private Vault repository.');
  }
}

/* ============================================================================
 * Pure Utilities (UTF-8, Base64, Canonical JSON, Date/Time Validation)
 * ============================================================================ */

function utf8ByteLength(str) {
  var text = String(str || '');
  if (typeof Utilities !== 'undefined' && Utilities && typeof Utilities.newBlob === 'function') {
    return Utilities.newBlob(text, 'text/plain; charset=utf-8').getBytes().length;
  }
  // Standard UTF-8 byte count fallback
  var bytes = 0;
  for (var i = 0; i < text.length; i++) {
    var code = text.charCodeAt(i);
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (code >= 0xD800 && code <= 0xDBFF) {
      bytes += 4;
      i++;
    } else bytes += 3;
  }
  return bytes;
}

function encodeBase64Utf8(str) {
  var bytes = Utilities.newBlob(String(str || ''), 'text/plain; charset=utf-8').getBytes();
  return Utilities.base64Encode(bytes);
}

function decodeBase64Utf8(base64Str) {
  var cleaned = String(base64Str || '').replace(/\s+/g, '');
  var bytes = Utilities.base64Decode(cleaned);
  return Utilities.newBlob(bytes).getDataAsString('UTF-8');
}

function isPlainObject(val) {
  return val !== null && typeof val === 'object' && !Array.isArray(val);
}

function canonicalizeValue(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalizeValue);
  }
  if (isPlainObject(value)) {
    var sorted = {};
    var keys = Object.keys(value).sort();
    for (var i = 0; i < keys.length; i++) {
      sorted[keys[i]] = canonicalizeValue(value[keys[i]]);
    }
    return sorted;
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(canonicalizeValue(value));
}

function isValidCalendarDate(year, month, day) {
  if (month < 1 || month > 12 || day < 1) return false;
  var daysInMonth = [31, (year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= daysInMonth[month - 1];
}

function isValidIsoDate(value) {
  if (typeof value !== 'string') return false;
  var m = ISO_DATE_RE.exec(value);
  if (!m) return false;
  return isValidCalendarDate(Number(m[1]), Number(m[2]), Number(m[3]));
}

function isValidIsoDateTimeWithTz(value) {
  if (typeof value !== 'string') return false;
  var m = ISO_DATETIME_TZ_RE.exec(value);
  if (!m) return false;
  var year = Number(m[1]);
  var month = Number(m[2]);
  var day = Number(m[3]);
  var hour = Number(m[4]);
  var minute = Number(m[5]);
  var second = Number(m[6]);
  if (!isValidCalendarDate(year, month, day)) return false;
  if (hour > 23 || minute > 59 || second > 59) return false;
  if (m[8] !== 'Z') {
    var tzHour = Number(m[10]);
    var tzMin = Number(m[11]);
    if (tzHour > 23 || tzMin > 59) return false;
  }
  return true;
}

function formatShanghaiNow() {
  var now = new Date();
  if (typeof Utilities !== 'undefined' && Utilities && typeof Utilities.formatDate === 'function') {
    return Utilities.formatDate(now, 'Asia/Shanghai', "yyyy-MM-dd'T'HH:mm:ss+08:00");
  }
  return now.toISOString();
}

function shortSha(sha) {
  return sha ? String(sha).slice(0, 7) : 'none';
}

function sanitizeErrorMessage(err, token) {
  var msg = err && err.message ? String(err.message) : String(err || 'unknown error');
  if (token) {
    msg = msg.split(token).join('[REDACTED]');
  }
  return msg.slice(0, 500);
}

/* ============================================================================
 * JSON Extraction & Curly-Quote Guard
 * ============================================================================ */

/**
 * Extracts a JSON object string from raw text (handles UTF-8 BOM, Markdown
 * ```json fences, or brief surrounding prose).
 */
function extractJsonBlock(rawText) {
  if (typeof rawText !== 'string') {
    return { ok: false, code: 'EMPTY_BODY', error: 'Body is not a string.' };
  }
  var text = rawText.replace(/^\uFEFF/, '').trim();
  if (!text) {
    return { ok: false, code: 'EMPTY_BODY', error: 'Body is empty.' };
  }

  // Prefer explicit fenced JSON block if present
  var fenceMatch = /```(?:json)?\s*\r?\n([\s\S]*?)\r?\n```/i.exec(text);
  if (fenceMatch && fenceMatch[1] && fenceMatch[1].trim()) {
    return { ok: true, jsonText: fenceMatch[1].trim() };
  }

  // Otherwise locate outermost braces
  var firstBrace = text.indexOf('{');
  var lastBrace = text.lastIndexOf('}');
  if (firstBrace === -1 || lastBrace === -1 || lastBrace <= firstBrace) {
    return { ok: false, code: 'NO_JSON_OBJECT', error: 'No JSON object ({...}) found in message body.' };
  }
  return { ok: true, jsonText: text.slice(firstBrace, lastBrace + 1).trim() };
}

/**
 * Parses JSON strictly:
 *   - Legal Chinese curly quotes (“”‘’) INSIDE JSON string values are valid JSON
 *     and preserved verbatim.
 *   - Structural curly quotes OUTSIDE double-quoted JSON strings (which break
 *     JSON syntax) are explicitly detected and rejected with position details.
 */
function parseJsonWithCurlyQuoteGuard(jsonText) {
  if (typeof jsonText !== 'string' || !jsonText.trim()) {
    return { ok: false, code: 'EMPTY_JSON', error: 'JSON text is empty.' };
  }
  try {
    var parsed = JSON.parse(jsonText);
    return { ok: true, value: parsed };
  } catch (parseErr) {
    // Scan outside ASCII double-quoted string literals for structural curly quotes
    var inString = false;
    var escaped = false;
    for (var i = 0; i < jsonText.length; i++) {
      var ch = jsonText.charAt(i);
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (ch === '\\') {
          escaped = true;
        } else if (ch === '"') {
          inString = false;
        }
      } else {
        if (ch === '"') {
          inString = true;
        } else if (STRUCTURAL_CURLY_QUOTES[ch]) {
          return {
            ok: false,
            code: 'STRUCTURAL_CURLY_QUOTE',
            error: 'JSON syntax broken by structural curly quote ' + ch + ' at position ' + i +
              ' (outside string literal). Use ASCII " for JSON syntax; Chinese quotes inside string values are preserved.'
          };
        }
      }
    }
    return {
      ok: false,
      code: 'INVALID_JSON',
      error: 'Invalid JSON syntax: ' + (parseErr && parseErr.message ? parseErr.message : String(parseErr))
    };
  }
}

/* ============================================================================
 * Local Schema Validators (Strict Parity with Core v0.5.1 + Vault Rules)
 * ============================================================================ */

function rejectExtraKeys(obj, allowedMap, path) {
  var keys = Object.keys(obj);
  var extra = [];
  for (var i = 0; i < keys.length; i++) {
    if (!allowedMap[keys[i]]) extra.push(keys[i]);
  }
  if (extra.length > 0) {
    extra.sort();
    throw new Error(path + ' has unsupported fields: ' + extra.join(', '));
  }
}

function requireKeys(obj, requiredList, path) {
  var missing = [];
  for (var i = 0; i < requiredList.length; i++) {
    if (!Object.prototype.hasOwnProperty.call(obj, requiredList[i])) {
      missing.push(requiredList[i]);
    }
  }
  if (missing.length > 0) {
    throw new Error(path + ' missing required fields: ' + missing.join(', '));
  }
}

function requireNonEmptyString(val, path, maxLen) {
  if (typeof val !== 'string' || !val.trim()) {
    throw new Error(path + ' must be a non-empty string');
  }
  if (maxLen && val.length > maxLen) {
    throw new Error(path + ' exceeds max length ' + maxLen);
  }
  return val;
}

function requireEnum(val, allowedMap, path) {
  if (typeof val !== 'string' || !allowedMap[val]) {
    throw new Error(path + ' must be one of: ' + Object.keys(allowedMap).sort().join(', '));
  }
  return val;
}

function requireNumber(val, path, min, max) {
  if (typeof val !== 'number' || !isFinite(val)) {
    throw new Error(path + ' must be a finite number');
  }
  if (min !== null && min !== undefined && val < min) {
    throw new Error(path + ' must be >= ' + min);
  }
  if (max !== null && max !== undefined && val > max) {
    throw new Error(path + ' must be <= ' + max);
  }
  return val;
}

function requireInteger(val, path, min, max) {
  if (typeof val !== 'number' || !isFinite(val) || Math.floor(val) !== val) {
    throw new Error(path + ' must be an integer');
  }
  if (min !== null && min !== undefined && val < min) {
    throw new Error(path + ' must be >= ' + min);
  }
  if (max !== null && max !== undefined && val > max) {
    throw new Error(path + ' must be <= ' + max);
  }
  return val;
}

function validateStringList(val, path, options) {
  var opts = options || {};
  var allowEmpty = Boolean(opts.allowEmpty);
  var pattern = opts.pattern || null;
  if (!Array.isArray(val) || (!allowEmpty && val.length === 0)) {
    throw new Error(path + ' must be ' + (allowEmpty ? 'an array' : 'a non-empty array'));
  }
  var seen = {};
  for (var i = 0; i < val.length; i++) {
    var item = val[i];
    if (typeof item !== 'string' || !item || (opts.requireTrimmed && !item.trim())) {
      throw new Error(path + ' must contain non-empty strings');
    }
    if (seen[item]) {
      throw new Error(path + ' must not contain duplicates');
    }
    seen[item] = true;
    if (pattern && !pattern.test(item)) {
      throw new Error(path + ' contains an invalid identifier');
    }
  }
  return val;
}

function rejectTranscriptFields(value, path) {
  if (isPlainObject(value)) {
    var keys = Object.keys(value);
    var found = [];
    for (var i = 0; i < keys.length; i++) {
      if (FORBIDDEN_TRANSCRIPT_FIELDS[keys[i]]) found.push(keys[i]);
    }
    if (found.length > 0) {
      found.sort();
      throw new Error(path + ' contains full-chat fields: ' + found.join(', '));
    }
    for (var j = 0; j < keys.length; j++) {
      rejectTranscriptFields(value[keys[j]], path + '.' + keys[j]);
    }
  } else if (Array.isArray(value)) {
    for (var k = 0; k < value.length; k++) {
      rejectTranscriptFields(value[k], path + '[' + k + ']');
    }
  }
}

function validateStudyRecordPayload(payload) {
  if (!isPlainObject(payload)) {
    throw new Error('study_record.payload must be an object');
  }
  var allowed = {
    summary: true,
    subject: true,
    subject_label: true,
    topic: true,
    source_ref: true,
    occurred_at: true,
    occurred_on: true
  };
  rejectExtraKeys(payload, allowed, 'study_record.payload');
  requireKeys(payload, ['summary'], 'study_record.payload');

  var textKeys = ['summary', 'subject', 'subject_label', 'topic', 'source_ref'];
  for (var i = 0; i < textKeys.length; i++) {
    var k = textKeys[i];
    if (Object.prototype.hasOwnProperty.call(payload, k)) {
      var v = requireNonEmptyString(payload[k], 'study_record.' + k, 12000);
      if (UNSAFE_JSONL_SEPARATORS_RE.test(v)) {
        throw new Error('study_record.' + k + ' contains Unicode line separator (U+2028/U+2029/U+0085), which breaks Core v0.5.1 JSONL reader');
      }
    }
  }
  if (Object.prototype.hasOwnProperty.call(payload, 'subject') &&
      Object.prototype.hasOwnProperty.call(payload, 'subject_label') &&
      payload.subject !== payload.subject_label) {
    throw new Error('study_record.subject and subject_label conflict');
  }
  if (Object.prototype.hasOwnProperty.call(payload, 'occurred_at') &&
      Object.prototype.hasOwnProperty.call(payload, 'occurred_on')) {
    throw new Error('study_record may specify occurred_at or occurred_on, not both');
  }
  if (Object.prototype.hasOwnProperty.call(payload, 'occurred_at')) {
    if (!isValidIsoDateTimeWithTz(payload.occurred_at)) {
      throw new Error('study_record.occurred_at must be an ISO-8601 datetime with timezone');
    }
  }
  if (Object.prototype.hasOwnProperty.call(payload, 'occurred_on')) {
    if (!isValidIsoDate(payload.occurred_on)) {
      throw new Error('study_record.occurred_on must be a valid YYYY-MM-DD date');
    }
  }
}

function validateChangeRequestPayload(payload) {
  if (!isPlainObject(payload)) {
    throw new Error('project_change_request payload must be an object');
  }
  var allowed = {
    title: true,
    description: true,
    requested_files: true,
    acceptance_criteria: true,
    compatibility_notes: true
  };
  rejectExtraKeys(payload, allowed, 'project_change_request');
  requireKeys(payload, ['title', 'description'], 'project_change_request');
  var strKeys = ['title', 'description', 'compatibility_notes'];
  for (var i = 0; i < strKeys.length; i++) {
    if (Object.prototype.hasOwnProperty.call(payload, strKeys[i])) {
      requireNonEmptyString(payload[strKeys[i]], 'project_change_request.' + strKeys[i]);
    }
  }
  var listKeys = ['requested_files', 'acceptance_criteria'];
  for (var j = 0; j < listKeys.length; j++) {
    var lk = listKeys[j];
    if (Object.prototype.hasOwnProperty.call(payload, lk)) {
      if (!Array.isArray(payload[lk])) {
        throw new Error('project_change_request.' + lk + ' must be an array of non-empty strings');
      }
      for (var m = 0; m < payload[lk].length; m++) {
        requireNonEmptyString(payload[lk][m], 'project_change_request.' + lk + '[' + m + ']');
      }
    }
  }
}

function validateKnowledgeUnit(unit) {
  if (!isPlainObject(unit)) throw new Error('knowledge_unit must be an object');
  var allowed = {
    schema_version: true, unit_id: true, subject: true, title: true, description: true,
    prerequisites: true, transfer_links: true, evidence_targets: true, exam_weight: true,
    estimated_minutes: true, status: true, tags: true
  };
  rejectExtraKeys(unit, allowed, 'knowledge_unit');
  requireKeys(unit, ['schema_version', 'unit_id', 'subject', 'title'], 'knowledge_unit');
  if (unit.schema_version !== '1.0') throw new Error("knowledge_unit.schema_version must be '1.0'");
  if (typeof unit.unit_id !== 'string' || !UNIT_ID_RE.test(unit.unit_id)) {
    throw new Error('knowledge_unit.unit_id has invalid format');
  }
  requireEnum(unit.subject, SUBJECTS, 'knowledge_unit.subject');
  requireNonEmptyString(unit.title, 'knowledge_unit.title');
  if (Object.prototype.hasOwnProperty.call(unit, 'prerequisites')) {
    validateStringList(unit.prerequisites, 'knowledge_unit.prerequisites', { pattern: UNIT_ID_RE, allowEmpty: true });
  }
  if (Object.prototype.hasOwnProperty.call(unit, 'transfer_links')) {
    validateStringList(unit.transfer_links, 'knowledge_unit.transfer_links', { pattern: UNIT_ID_RE, allowEmpty: true });
  }
  if (Object.prototype.hasOwnProperty.call(unit, 'evidence_targets')) {
    var targets = validateStringList(unit.evidence_targets, 'knowledge_unit.evidence_targets');
    for (var i = 0; i < targets.length; i++) {
      requireEnum(targets[i], EVIDENCE_TARGETS, 'knowledge_unit.evidence_targets[]');
    }
  }
  if (Object.prototype.hasOwnProperty.call(unit, 'exam_weight')) {
    requireNumber(unit.exam_weight, 'knowledge_unit.exam_weight', 0, 1);
  }
  if (Object.prototype.hasOwnProperty.call(unit, 'estimated_minutes')) {
    requireInteger(unit.estimated_minutes, 'knowledge_unit.estimated_minutes', 1, null);
  }
  if (Object.prototype.hasOwnProperty.call(unit, 'status')) {
    requireEnum(unit.status, { active: true, archived: true }, 'knowledge_unit.status');
  }
  if (Object.prototype.hasOwnProperty.call(unit, 'description') && typeof unit.description !== 'string') {
    throw new Error('knowledge_unit.description must be a string');
  }
  if (Object.prototype.hasOwnProperty.call(unit, 'tags')) {
    validateStringList(unit.tags, 'knowledge_unit.tags', { allowEmpty: true });
  }
}

function validateAttempt(attempt) {
  if (!isPlainObject(attempt)) throw new Error('attempt must be an object');
  var allowed = {
    question_id: true, result: true, answer_mode: true, process_check: true, assistance_level: true,
    time_minutes: true, confidence_before: true, confidence_after: true, evidence: true,
    variant_level: true, parent_diagnosis_id: true, delayed_days: true
  };
  rejectExtraKeys(attempt, allowed, 'attempt');
  requireKeys(attempt, ['question_id', 'result', 'answer_mode', 'process_check', 'assistance_level'], 'attempt');
  requireNonEmptyString(attempt.question_id, 'attempt.question_id');
  requireEnum(attempt.result, RESULTS, 'attempt.result');
  requireEnum(attempt.answer_mode, ANSWER_MODES, 'attempt.answer_mode');
  requireEnum(attempt.process_check, PROCESS_CHECKS, 'attempt.process_check');
  requireInteger(attempt.assistance_level, 'attempt.assistance_level', 0, 5);
  if (Object.prototype.hasOwnProperty.call(attempt, 'time_minutes')) {
    requireNumber(attempt.time_minutes, 'attempt.time_minutes', 0.000001, null);
  }
  if (Object.prototype.hasOwnProperty.call(attempt, 'confidence_before')) {
    requireNumber(attempt.confidence_before, 'attempt.confidence_before', 0, 1);
  }
  if (Object.prototype.hasOwnProperty.call(attempt, 'confidence_after')) {
    requireNumber(attempt.confidence_after, 'attempt.confidence_after', 0, 1);
  }
  if (Object.prototype.hasOwnProperty.call(attempt, 'variant_level')) {
    requireEnum(attempt.variant_level, VARIANT_LEVELS, 'attempt.variant_level');
    if (!Object.prototype.hasOwnProperty.call(attempt, 'parent_diagnosis_id')) {
      throw new Error('variant attempt needs parent_diagnosis_id');
    }
  }
  if (Object.prototype.hasOwnProperty.call(attempt, 'delayed_days')) {
    requireInteger(attempt.delayed_days, 'attempt.delayed_days', 0, null);
  }
  if (Object.prototype.hasOwnProperty.call(attempt, 'evidence')) {
    requireNonEmptyString(attempt.evidence, 'attempt.evidence');
  }
  if (Object.prototype.hasOwnProperty.call(attempt, 'parent_diagnosis_id')) {
    requireNonEmptyString(attempt.parent_diagnosis_id, 'attempt.parent_diagnosis_id');
  }
  if (attempt.answer_mode === 'independent' && attempt.assistance_level !== 0) {
    throw new Error('independent attempt must have assistance_level 0');
  }
}

function validateDiagnosis(diagnosis) {
  if (!isPlainObject(diagnosis)) throw new Error('diagnosis must be an object');
  var allowed = {
    diagnosis_id: true, question_id: true, status: true, generated_by: true, confidence: true,
    first_divergence: true, root_cause: true, error_tags: true, evidence_refs: true,
    learner_verdict: true, confirmation_method: true, supersedes_event_id: true, next_action: true
  };
  rejectExtraKeys(diagnosis, allowed, 'diagnosis');
  requireKeys(diagnosis, ['diagnosis_id', 'question_id', 'status', 'generated_by'], 'diagnosis');
  requireNonEmptyString(diagnosis.diagnosis_id, 'diagnosis.diagnosis_id');
  requireNonEmptyString(diagnosis.question_id, 'diagnosis.question_id');
  requireEnum(diagnosis.status, DIAGNOSIS_STATUSES, 'diagnosis.status');
  requireEnum(diagnosis.generated_by, DIAGNOSIS_GENERATORS, 'diagnosis.generated_by');
  if (Object.prototype.hasOwnProperty.call(diagnosis, 'confidence')) {
    requireNumber(diagnosis.confidence, 'diagnosis.confidence', 0, 1);
  }
  var strFields = ['first_divergence', 'root_cause', 'learner_verdict', 'supersedes_event_id', 'next_action'];
  for (var i = 0; i < strFields.length; i++) {
    if (Object.prototype.hasOwnProperty.call(diagnosis, strFields[i])) {
      requireNonEmptyString(diagnosis[strFields[i]], 'diagnosis.' + strFields[i]);
    }
  }
  if (Object.prototype.hasOwnProperty.call(diagnosis, 'error_tags')) {
    validateStringList(diagnosis.error_tags, 'diagnosis.error_tags');
  }
  if (Object.prototype.hasOwnProperty.call(diagnosis, 'evidence_refs')) {
    validateStringList(diagnosis.evidence_refs, 'diagnosis.evidence_refs');
  }
  if (Object.prototype.hasOwnProperty.call(diagnosis, 'confirmation_method')) {
    requireEnum(diagnosis.confirmation_method, CONFIRMATION_METHODS, 'diagnosis.confirmation_method');
  }
  if (diagnosis.status === 'confirmed') {
    if (!diagnosis.first_divergence && !diagnosis.root_cause) {
      throw new Error('confirmed diagnosis needs first_divergence or root_cause');
    }
    if (!diagnosis.learner_verdict) {
      throw new Error('confirmed diagnosis needs learner_verdict');
    }
    if (!diagnosis.confirmation_method || diagnosis.confirmation_method === 'not_confirmed') {
      throw new Error('confirmed diagnosis needs a valid confirmation_method');
    }
  }
}

function validateLearningEvent(event, expectedType) {
  if (!isPlainObject(event)) throw new Error('learning_event must be an object');
  var allowed = {
    schema_version: true, event_id: true, timestamp: true, event_type: true, subject: true,
    unit_ids: true, activity: true, source_ref: true, source_hash: true, transcription: true,
    transcription_uncertainty: true, attempt: true, diagnosis: true, next_action: true,
    recommended_review_at: true
  };
  rejectExtraKeys(event, allowed, 'learning_event');
  requireKeys(event, ['schema_version', 'event_id', 'timestamp', 'event_type', 'subject', 'unit_ids'], 'learning_event');
  if (event.schema_version !== '1.0') throw new Error("learning_event.schema_version must be '1.0'");
  if (typeof event.event_id !== 'string' || !EVENT_ID_RE.test(event.event_id)) {
    throw new Error('learning_event.event_id must be non-empty and contain no whitespace');
  }
  if (!isValidIsoDateTimeWithTz(event.timestamp)) {
    throw new Error('learning_event.timestamp must be an ISO-8601 datetime with timezone');
  }
  requireEnum(event.event_type, EVENT_TYPES, 'learning_event.event_type');
  if (expectedType && event.event_type !== expectedType) {
    throw new Error('operation requires event_type=' + expectedType);
  }
  requireEnum(event.subject, SUBJECTS, 'learning_event.subject');
  validateStringList(event.unit_ids, 'learning_event.unit_ids', { pattern: UNIT_ID_RE });
  if (Object.prototype.hasOwnProperty.call(event, 'source_hash') &&
      (typeof event.source_hash !== 'string' || !SHA256_RE.test(event.source_hash))) {
    throw new Error('learning_event.source_hash must be a SHA-256 hex digest');
  }
  if (Object.prototype.hasOwnProperty.call(event, 'recommended_review_at') &&
      !isValidIsoDateTimeWithTz(event.recommended_review_at)) {
    throw new Error('learning_event.recommended_review_at must be an ISO-8601 datetime with timezone');
  }
  if (Object.prototype.hasOwnProperty.call(event, 'source_ref')) {
    requireNonEmptyString(event.source_ref, 'learning_event.source_ref');
  }
  if (Object.prototype.hasOwnProperty.call(event, 'next_action')) {
    requireNonEmptyString(event.next_action, 'learning_event.next_action');
  }
  if (Object.prototype.hasOwnProperty.call(event, 'transcription') && typeof event.transcription !== 'string') {
    throw new Error('learning_event.transcription must be a string');
  }
  if (Object.prototype.hasOwnProperty.call(event, 'transcription_uncertainty')) {
    validateStringList(event.transcription_uncertainty, 'learning_event.transcription_uncertainty', { allowEmpty: true });
  }
  if (event.event_type === 'attempt') {
    if (Object.prototype.hasOwnProperty.call(event, 'diagnosis')) {
      throw new Error('attempt event cannot contain diagnosis');
    }
    requireKeys(event, ['activity', 'attempt'], 'learning_event');
    requireEnum(event.activity, ACTIVITIES, 'learning_event.activity');
    validateAttempt(event.attempt);
  } else {
    if (Object.prototype.hasOwnProperty.call(event, 'attempt')) {
      throw new Error('diagnosis event cannot contain attempt');
    }
    requireKeys(event, ['diagnosis'], 'learning_event');
    validateDiagnosis(event.diagnosis);
  }
}

function validateSourceReference(ref) {
  if (!isPlainObject(ref)) throw new Error('source_reference must be an object');
  var allowed = {
    reference_id: true, kind: true, label: true, locator: true,
    edition: true, local_path: true, source_hash: true, notes: true
  };
  rejectExtraKeys(ref, allowed, 'source_reference');
  requireKeys(ref, ['reference_id', 'kind', 'label'], 'source_reference');
  if (typeof ref.reference_id !== 'string' || !EVENT_ID_RE.test(ref.reference_id)) {
    throw new Error('source_reference.reference_id must be non-empty and contain no whitespace');
  }
  requireEnum(ref.kind, SOURCE_KINDS, 'source_reference.kind');
  var strFields = ['label', 'locator', 'edition', 'local_path', 'notes'];
  for (var i = 0; i < strFields.length; i++) {
    if (Object.prototype.hasOwnProperty.call(ref, strFields[i])) {
      requireNonEmptyString(ref[strFields[i]], 'source_reference.' + strFields[i]);
    }
  }
  if (Object.prototype.hasOwnProperty.call(ref, 'source_hash') &&
      (typeof ref.source_hash !== 'string' || !SHA256_RE.test(ref.source_hash))) {
    throw new Error('source_reference.source_hash must be a SHA-256 hex digest');
  }
}

function validateSchedulerRequest(req) {
  if (!isPlainObject(req)) throw new Error('scheduler_request must be an object');
  requireKeys(req, ['schema_version', 'available_minutes', 'as_of'], 'scheduler_request');
  if (req.schema_version !== '1.0') throw new Error("scheduler_request.schema_version must be '1.0'");
  requireInteger(req.available_minutes, 'scheduler_request.available_minutes', 1, null);
  if (!isValidIsoDateTimeWithTz(req.as_of)) {
    throw new Error('scheduler_request.as_of must be an ISO-8601 datetime with timezone');
  }
  if (Object.prototype.hasOwnProperty.call(req, 'max_subject_share')) {
    var share = requireNumber(req.max_subject_share, 'scheduler_request.max_subject_share', 0, 1);
    if (share <= 0) throw new Error('scheduler_request.max_subject_share must be > 0');
  }
  if (Object.prototype.hasOwnProperty.call(req, 'phase_subjects')) {
    var subjects = validateStringList(req.phase_subjects, 'scheduler_request.phase_subjects');
    for (var i = 0; i < subjects.length; i++) {
      requireEnum(subjects[i], SUBJECTS, 'scheduler_request.phase_subjects[]');
    }
  }
  if (Object.prototype.hasOwnProperty.call(req, 'candidates')) {
    if (!Array.isArray(req.candidates)) throw new Error('scheduler_request.candidates must be an array');
    for (var j = 0; j < req.candidates.length; j++) {
      var cand = req.candidates[j];
      if (!isPlainObject(cand)) throw new Error('candidate must be an object');
      requireKeys(cand, ['task_id', 'subject', 'estimated_minutes'], 'candidate');
      requireNonEmptyString(cand.task_id, 'candidate.task_id');
      requireEnum(cand.subject, SUBJECTS, 'candidate.subject');
      requireInteger(cand.estimated_minutes, 'candidate.estimated_minutes', 1, null);
      if (Object.prototype.hasOwnProperty.call(cand, 'task_type')) {
        requireEnum(cand.task_type, TASK_TYPES, 'candidate.task_type');
      }
      if (Object.prototype.hasOwnProperty.call(cand, 'activity')) {
        requireEnum(cand.activity, ACTIVITIES, 'candidate.activity');
      }
    }
  }
}

function validateCoreMobileRequest(req) {
  if (!isPlainObject(req)) {
    throw new Error('mobile_request must be an object');
  }
  var allowed = {
    schema_version: true,
    request_id: true,
    created_at: true,
    operation: true,
    payload: true,
    client: true
  };
  rejectExtraKeys(req, allowed, 'mobile_request');
  requireKeys(req, ['schema_version', 'request_id', 'created_at', 'operation', 'payload'], 'mobile_request');
  if (req.schema_version !== '1.0') {
    throw new Error("mobile_request.schema_version must be '1.0'");
  }
  if (typeof req.request_id !== 'string' || !REQUEST_ID_RE.test(req.request_id)) {
    throw new Error('mobile_request.request_id must be a safe path component up to 128 characters');
  }
  if (!isValidIsoDateTimeWithTz(req.created_at)) {
    throw new Error('mobile_request.created_at must be an ISO-8601 datetime with timezone');
  }
  requireEnum(req.operation, CORE_OPERATIONS, 'mobile_request.operation');
  if (!isPlainObject(req.payload)) {
    throw new Error('mobile_request.payload must be an object');
  }
  if (Object.prototype.hasOwnProperty.call(req, 'client')) {
    requireNonEmptyString(req.client, 'mobile_request.client');
  }

  rejectTranscriptFields(req.payload, 'payload');

  switch (req.operation) {
    case 'save_study_record':
      validateStudyRecordPayload(req.payload);
      break;
    case 'project_change_request':
      validateChangeRequestPayload(req.payload);
      break;
    case 'record_attempt':
    case 'record_contest_baseline':
      if (!isPlainObject(req.payload.event)) throw new Error('payload.event must be an object');
      validateLearningEvent(req.payload.event, 'attempt');
      break;
    case 'record_diagnosis':
      if (!isPlainObject(req.payload.event)) throw new Error('payload.event must be an object');
      validateLearningEvent(req.payload.event, 'diagnosis');
      break;
    case 'register_unit':
      if (!isPlainObject(req.payload.unit)) throw new Error('payload.unit must be an object');
      validateKnowledgeUnit(req.payload.unit);
      break;
    case 'save_session_result':
      if (!Array.isArray(req.payload.events) || req.payload.events.length === 0) {
        throw new Error('save_session_result.payload.events must be a non-empty array');
      }
      var seenEventIds = {};
      for (var i = 0; i < req.payload.events.length; i++) {
        validateLearningEvent(req.payload.events[i], null);
        var eid = req.payload.events[i].event_id;
        if (seenEventIds[eid]) throw new Error('duplicate event_id in save_session_result: ' + eid);
        seenEventIds[eid] = true;
      }
      break;
    case 'update_source_reference':
      if (!isPlainObject(req.payload.reference)) throw new Error('payload.reference must be an object');
      validateSourceReference(req.payload.reference);
      break;
    case 'request_schedule':
      if (!isPlainObject(req.payload.request)) throw new Error('payload.request must be an object');
      validateSchedulerRequest(req.payload.request);
      break;
    default:
      throw new Error('Unsupported operation: ' + req.operation);
  }
}

/**
 * Validates the unified bridge envelope for [POSTGRAD-INBOX]:
 *   { "target": "inbox/<request_id>.json", "request_id": "<request_id>", "payload": { ... } }
 */
function validateInboxEnvelope(envelope, options) {
  var opts = options || {};
  var maxBytes = opts.maxBytes || DEFAULT_CONFIG.MAX_INBOX_BYTES;

  if (!isPlainObject(envelope)) {
    return { ok: false, code: 'INVALID_ENVELOPE', error: 'Bridge envelope must be a JSON object.' };
  }
  try {
    rejectExtraKeys(envelope, { target: true, request_id: true, payload: true }, 'bridge_envelope');
    requireKeys(envelope, ['target', 'request_id', 'payload'], 'bridge_envelope');

    if (typeof envelope.target !== 'string') {
      throw new Error('bridge_envelope.target must be a string');
    }
    var targetMatch = INBOX_TARGET_RE.exec(envelope.target);
    if (!targetMatch) {
      throw new Error('Path whitelist violation: [POSTGRAD-INBOX] target must match inbox/<request_id>.json');
    }
    var targetStem = targetMatch[1];

    if (typeof envelope.request_id !== 'string' || !REQUEST_ID_RE.test(envelope.request_id)) {
      throw new Error('bridge_envelope.request_id has invalid format');
    }
    if (envelope.request_id !== targetStem) {
      throw new Error('bridge_envelope.request_id (' + envelope.request_id + ') does not match target filename (' + targetStem + ')');
    }

    validateCoreMobileRequest(envelope.payload);

    if (envelope.payload.request_id !== envelope.request_id) {
      throw new Error('payload.request_id (' + envelope.payload.request_id + ') does not match bridge_envelope.request_id (' + envelope.request_id + ')');
    }

    var serialized = JSON.stringify(envelope.payload, null, 2) + '\n';
    var byteLen = utf8ByteLength(serialized);
    if (byteLen > maxBytes) {
      throw new Error('Payload exceeds maximum allowed size (' + byteLen + ' > ' + maxBytes + ' bytes)');
    }

    return {
      ok: true,
      kind: 'inbox',
      target: envelope.target,
      requestId: envelope.request_id,
      payload: envelope.payload,
      serialized: serialized,
      bytes: byteLen
    };
  } catch (err) {
    return { ok: false, code: 'VALIDATION_FAILED', error: err.message || String(err) };
  }
}

/**
 * Parses YAML frontmatter at the start of analysis/learner_context.md.
 */
function parseSimpleFrontmatter(markdown) {
  if (typeof markdown !== 'string') return null;
  var m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(markdown);
  if (!m) return null;
  var lines = m[1].split(/\r?\n/);
  var data = {};
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim();
    if (!line || line.charAt(0) === '#') continue;
    var sep = line.indexOf(':');
    if (sep <= 0) continue;
    var key = line.slice(0, sep).trim();
    var rawVal = line.slice(sep + 1).trim();
    if ((rawVal.charAt(0) === '"' && rawVal.charAt(rawVal.length - 1) === '"') ||
        (rawVal.charAt(0) === "'" && rawVal.charAt(rawVal.length - 1) === "'")) {
      rawVal = rawVal.slice(1, -1);
    }
    data[key] = rawVal;
  }
  return data;
}

/**
 * Validates the unified bridge envelope for [POSTGRAD-REVIEW] (authorized daily
 * qualitative review role under docs/DAILY_REVIEW.md):
 *   {
 *     "target": "analysis/daily/YYYY-MM-DD.md",
 *     "request_id": "review-YYYY-MM-DD",
 *     "payload": {
 *       "review_date": "YYYY-MM-DD",
 *       "daily_report_path": "analysis/daily/YYYY-MM-DD.md",
 *       "daily_report_markdown": "...",
 *       "learner_context_path": "analysis/learner_context.md",
 *       "learner_context_markdown": "...",
 *       "allow_same_day_update": false
 *     }
 *   }
 */
function validateReviewEnvelope(envelope, options) {
  var opts = options || {};
  var maxReportBytes = opts.maxReportBytes || DEFAULT_CONFIG.MAX_REVIEW_REPORT_BYTES;
  var maxContextBytes = opts.maxContextBytes || DEFAULT_CONFIG.MAX_REVIEW_CONTEXT_BYTES;

  if (!isPlainObject(envelope)) {
    return { ok: false, code: 'INVALID_ENVELOPE', error: 'Review bridge envelope must be a JSON object.' };
  }
  try {
    rejectExtraKeys(envelope, { target: true, request_id: true, payload: true }, 'review_envelope');
    requireKeys(envelope, ['target', 'request_id', 'payload'], 'review_envelope');

    if (typeof envelope.target !== 'string') {
      throw new Error('review_envelope.target must be a string');
    }
    var targetMatch = REVIEW_TARGET_RE.exec(envelope.target);
    if (!targetMatch || !isValidIsoDate(targetMatch[1])) {
      throw new Error('Path whitelist violation: [POSTGRAD-REVIEW] target must match analysis/daily/YYYY-MM-DD.md with a valid date');
    }
    var targetDate = targetMatch[1];

    if (typeof envelope.request_id !== 'string' || !REVIEW_REQUEST_ID_RE.test(envelope.request_id)) {
      throw new Error('review_envelope.request_id must match review-YYYY-MM-DD');
    }

    var p = envelope.payload;
    if (!isPlainObject(p)) throw new Error('review_envelope.payload must be an object');
    rejectExtraKeys(p, {
      review_date: true,
      daily_report_path: true,
      daily_report_markdown: true,
      learner_context_path: true,
      learner_context_markdown: true,
      allow_same_day_update: true
    }, 'review_envelope.payload');
    requireKeys(p, [
      'review_date',
      'daily_report_path',
      'daily_report_markdown',
      'learner_context_path',
      'learner_context_markdown'
    ], 'review_envelope.payload');

    if (p.review_date !== targetDate) {
      throw new Error('payload.review_date (' + p.review_date + ') must match target date (' + targetDate + ')');
    }
    if (p.daily_report_path !== envelope.target) {
      throw new Error('payload.daily_report_path must equal review_envelope.target');
    }
    if (p.learner_context_path !== 'analysis/learner_context.md') {
      throw new Error('Path whitelist violation: learner_context_path must be literally analysis/learner_context.md');
    }
    if (Object.prototype.hasOwnProperty.call(p, 'allow_same_day_update') &&
        typeof p.allow_same_day_update !== 'boolean') {
      throw new Error('payload.allow_same_day_update must be a boolean');
    }

    requireNonEmptyString(p.daily_report_markdown, 'payload.daily_report_markdown');
    requireNonEmptyString(p.learner_context_markdown, 'payload.learner_context_markdown');
    if (p.daily_report_markdown.trim().length < 80) {
      throw new Error('payload.daily_report_markdown is too short (< 80 chars); refusing blank/stub report');
    }
    if (p.learner_context_markdown.trim().length < 80) {
      throw new Error('payload.learner_context_markdown is too short (< 80 chars); refusing blank context overwrite');
    }

    var reportBytes = utf8ByteLength(p.daily_report_markdown);
    if (reportBytes > maxReportBytes) {
      throw new Error('daily_report_markdown exceeds max size (' + reportBytes + ' > ' + maxReportBytes + ' bytes)');
    }
    var contextBytes = utf8ByteLength(p.learner_context_markdown);
    if (contextBytes > maxContextBytes) {
      throw new Error('learner_context_markdown exceeds max size (' + contextBytes + ' > ' + maxContextBytes + ' bytes)');
    }

    var fm = parseSimpleFrontmatter(p.learner_context_markdown);
    if (!fm) {
      throw new Error('learner_context_markdown must start with YAML frontmatter (--- ... ---)');
    }
    if (fm.analysis_type !== 'llm_qualitative_review') {
      throw new Error('learner_context frontmatter analysis_type must be llm_qualitative_review');
    }
    if (!fm.reviewer || !String(fm.reviewer).trim()) {
      throw new Error('learner_context frontmatter must include non-empty reviewer');
    }
    if (!isValidIsoDateTimeWithTz(fm.reviewed_at)) {
      throw new Error('learner_context frontmatter reviewed_at must be ISO-8601 with timezone');
    }
    if (fm.review_report !== envelope.target) {
      throw new Error('learner_context frontmatter review_report must match ' + envelope.target);
    }
    var studyCount = Number(fm.study_record_count);
    var eventCount = Number(fm.formal_event_count);
    if (!isFinite(studyCount) || studyCount < 0 || Math.floor(studyCount) !== studyCount) {
      throw new Error('learner_context frontmatter study_record_count must be a non-negative integer');
    }
    if (!isFinite(eventCount) || eventCount < 0 || Math.floor(eventCount) !== eventCount) {
      throw new Error('learner_context frontmatter formal_event_count must be a non-negative integer');
    }
    if (!fm.last_record_id || !String(fm.last_record_id).trim()) {
      throw new Error('learner_context frontmatter must include last_record_id');
    }
    if (!fm.last_event_id || !String(fm.last_event_id).trim()) {
      throw new Error('learner_context frontmatter must include last_event_id');
    }

    var reportText = p.daily_report_markdown.replace(/\r\n/g, '\n');
    if (!reportText.endsWith('\n')) reportText += '\n';
    var contextText = p.learner_context_markdown.replace(/\r\n/g, '\n');
    if (!contextText.endsWith('\n')) contextText += '\n';

    return {
      ok: true,
      kind: 'review',
      target: envelope.target,
      requestId: envelope.request_id,
      reviewDate: targetDate,
      dailyReportPath: p.daily_report_path,
      dailyReportMarkdown: reportText,
      learnerContextPath: p.learner_context_path,
      learnerContextMarkdown: contextText,
      allowSameDayUpdate: Boolean(p.allow_same_day_update),
      frontmatter: {
        study_record_count: studyCount,
        formal_event_count: eventCount,
        last_record_id: fm.last_record_id,
        last_event_id: fm.last_event_id,
        reviewer: fm.reviewer,
        reviewed_at: fm.reviewed_at
      }
    };
  } catch (err) {
    return { ok: false, code: 'REVIEW_VALIDATION_FAILED', error: err.message || String(err) };
  }
}

/* ============================================================================
 * GitHub REST API Client (Single-Repo Fine-Grained PAT, Non-Overwrite Guards)
 * ============================================================================ */

function githubRequest(cfg, method, path, bodyObj) {
  var url = 'https://api.github.com/repos/' +
    encodeURIComponent(cfg.githubOwner) + '/' +
    encodeURIComponent(cfg.githubRepo) + path;

  var options = {
    method: method,
    muteHttpExceptions: true,
    headers: {
      Authorization: 'Bearer ' + cfg.githubToken,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'postgrad-google-bridge/' + BRIDGE_VERSION
    }
  };
  if (bodyObj !== undefined && bodyObj !== null) {
    options.contentType = 'application/json; charset=utf-8';
    options.payload = JSON.stringify(bodyObj);
  }
  var response = UrlFetchApp.fetch(url, options);
  var code = response.getResponseCode();
  var text = response.getContentText() || '';
  var json = null;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch (_e) {
      json = null;
    }
  }
  return { code: code, text: text, json: json };
}

function encodeRepoPath(repoPath) {
  return String(repoPath).split('/').map(encodeURIComponent).join('/');
}

function githubGetContent(cfg, repoPath) {
  var res = githubRequest(
    cfg,
    'get',
    '/contents/' + encodeRepoPath(repoPath) + '?ref=' + encodeURIComponent(cfg.githubBranch),
    null
  );
  if (res.code === 404) {
    return { status: 'not_found', code: 404 };
  }
  if (res.code === 200 && res.json && typeof res.json.content === 'string') {
    return {
      status: 'found',
      code: 200,
      sha: res.json.sha,
      content: decodeBase64Utf8(res.json.content)
    };
  }
  return {
    status: 'error',
    code: res.code,
    transient: res.code >= 500 || res.code === 429 || res.code === 403,
    error: 'GitHub GET ' + repoPath + ' failed (HTTP ' + res.code + ')'
  };
}

/**
 * Uploads an inbox/<request_id>.json file with strict GET-before-PUT guard:
 *   - Existing identical canonical JSON -> idempotent_skip (never overwrites)
 *   - Existing different JSON -> conflict (rejected, never overwrites)
 *   - Missing -> PUT without sha (atomic create)
 *   - 422 race -> re-GET and classify identical vs conflict
 */
function uploadInboxToGitHub(cfg, validated) {
  var existing = githubGetContent(cfg, validated.target);
  if (existing.status === 'error') {
    return { outcome: existing.transient ? 'transient_error' : 'rejected', error: existing.error };
  }
  if (existing.status === 'found') {
    return classifyExistingInboxFile(existing.content, validated.payload, validated.target);
  }

  var putBody = {
    message: 'bridge: add ' + validated.target,
    content: encodeBase64Utf8(validated.serialized),
    branch: cfg.githubBranch
  };
  var putRes = githubRequest(cfg, 'put', '/contents/' + encodeRepoPath(validated.target), putBody);
  if (putRes.code === 200 || putRes.code === 201) {
    return {
      outcome: 'uploaded',
      commitSha: putRes.json && putRes.json.commit ? putRes.json.commit.sha : null
    };
  }
  if (putRes.code === 422 || putRes.code === 409) {
    // Possible concurrent creation race: re-GET and verify
    var recheck = githubGetContent(cfg, validated.target);
    if (recheck.status === 'found') {
      return classifyExistingInboxFile(recheck.content, validated.payload, validated.target);
    }
    return {
      outcome: 'transient_error',
      error: 'GitHub PUT race on ' + validated.target + ' (HTTP ' + putRes.code + ')'
    };
  }
  return {
    outcome: (putRes.code >= 500 || putRes.code === 429) ? 'transient_error' : 'rejected',
    error: 'GitHub PUT ' + validated.target + ' failed (HTTP ' + putRes.code + ')'
  };
}

function classifyExistingInboxFile(existingText, incomingPayload, targetPath) {
  try {
    var existingObj = JSON.parse(existingText);
    if (canonicalJson(existingObj) === canonicalJson(incomingPayload)) {
      return { outcome: 'idempotent_skip', detail: 'Identical request already exists at ' + targetPath };
    }
    return {
      outcome: 'conflict',
      error: 'Conflict: ' + targetPath + ' already exists on GitHub with different content. Refusing to overwrite.'
    };
  } catch (_e) {
    return {
      outcome: 'conflict',
      error: 'Conflict: ' + targetPath + ' already exists on GitHub (non-JSON). Refusing to overwrite.'
    };
  }
}

/**
 * Publishes the two authorized daily review files atomically in a single
 * non-force commit via GitHub Git Data API, with non-regression and same-day
 * conflict protection.
 */
function publishDailyReviewToGitHub(cfg, validated) {
  if (!cfg.allowDailyReviewPublish) {
    return { outcome: 'rejected', error: 'Daily review publishing is disabled by ScriptProperty ALLOW_DAILY_REVIEW_PUBLISH=false.' };
  }

  var existingReport = githubGetContent(cfg, validated.dailyReportPath);
  if (existingReport.status === 'error') {
    return { outcome: existingReport.transient ? 'transient_error' : 'rejected', error: existingReport.error };
  }
  var existingContext = githubGetContent(cfg, validated.learnerContextPath);
  if (existingContext.status === 'error') {
    return { outcome: existingContext.transient ? 'transient_error' : 'rejected', error: existingContext.error };
  }

  // Idempotent skip if both files already match verbatim
  if (existingReport.status === 'found' && existingContext.status === 'found' &&
      existingReport.content.replace(/\r\n/g, '\n') === validated.dailyReportMarkdown &&
      existingContext.content.replace(/\r\n/g, '\n') === validated.learnerContextMarkdown) {
    return { outcome: 'idempotent_skip', detail: 'Identical daily review and learner context already published.' };
  }

  // Same-day overwrite guard
  if (existingReport.status === 'found' &&
      existingReport.content.replace(/\r\n/g, '\n') !== validated.dailyReportMarkdown &&
      !validated.allowSameDayUpdate) {
    return {
      outcome: 'conflict',
      error: 'Conflict: ' + validated.dailyReportPath + ' already exists with different content (set allow_same_day_update: true only after reading existing same-day report).'
    };
  }

  // Non-regression guard on learner_context.md coverage counts
  if (existingContext.status === 'found') {
    var prevFm = parseSimpleFrontmatter(existingContext.content);
    if (prevFm) {
      var prevStudy = Number(prevFm.study_record_count);
      var prevEvents = Number(prevFm.formal_event_count);
      if (isFinite(prevStudy) && validated.frontmatter.study_record_count < prevStudy) {
        return {
          outcome: 'rejected',
          error: 'Regression guard: new study_record_count (' + validated.frontmatter.study_record_count +
            ') is lower than existing (' + prevStudy + ').'
        };
      }
      if (isFinite(prevEvents) && validated.frontmatter.formal_event_count < prevEvents) {
        return {
          outcome: 'rejected',
          error: 'Regression guard: new formal_event_count (' + validated.frontmatter.formal_event_count +
            ') is lower than existing (' + prevEvents + ').'
        };
      }
    }
  }

  // Atomic 2-file commit via Git Data API with bounded 3 retries on non-fast-forward
  for (var attempt = 1; attempt <= 3; attempt++) {
    var refRes = githubRequest(cfg, 'get', '/git/ref/heads/' + encodeURIComponent(cfg.githubBranch), null);
    if (refRes.code !== 200 || !refRes.json || !refRes.json.object || !refRes.json.object.sha) {
      return { outcome: 'transient_error', error: 'Failed to read main ref (HTTP ' + refRes.code + ')' };
    }
    var baseCommitSha = refRes.json.object.sha;

    var commitRes = githubRequest(cfg, 'get', '/git/commits/' + baseCommitSha, null);
    if (commitRes.code !== 200 || !commitRes.json || !commitRes.json.tree || !commitRes.json.tree.sha) {
      return { outcome: 'transient_error', error: 'Failed to read base commit tree (HTTP ' + commitRes.code + ')' };
    }
    var baseTreeSha = commitRes.json.tree.sha;

    var reportBlobRes = githubRequest(cfg, 'post', '/git/blobs', {
      content: encodeBase64Utf8(validated.dailyReportMarkdown),
      encoding: 'base64'
    });
    if (reportBlobRes.code !== 201 || !reportBlobRes.json || !reportBlobRes.json.sha) {
      return { outcome: 'transient_error', error: 'Failed to create daily report blob (HTTP ' + reportBlobRes.code + ')' };
    }

    var contextBlobRes = githubRequest(cfg, 'post', '/git/blobs', {
      content: encodeBase64Utf8(validated.learnerContextMarkdown),
      encoding: 'base64'
    });
    if (contextBlobRes.code !== 201 || !contextBlobRes.json || !contextBlobRes.json.sha) {
      return { outcome: 'transient_error', error: 'Failed to create learner context blob (HTTP ' + contextBlobRes.code + ')' };
    }

    var treeRes = githubRequest(cfg, 'post', '/git/trees', {
      base_tree: baseTreeSha,
      tree: [
        {
          path: validated.dailyReportPath,
          mode: '100644',
          type: 'blob',
          sha: reportBlobRes.json.sha
        },
        {
          path: validated.learnerContextPath,
          mode: '100644',
          type: 'blob',
          sha: contextBlobRes.json.sha
        }
      ]
    });
    if (treeRes.code !== 201 || !treeRes.json || !treeRes.json.sha) {
      return { outcome: 'transient_error', error: 'Failed to create Git tree (HTTP ' + treeRes.code + ')' };
    }

    var newCommitRes = githubRequest(cfg, 'post', '/git/commits', {
      message: 'bridge: publish daily review ' + validated.reviewDate,
      tree: treeRes.json.sha,
      parents: [baseCommitSha]
    });
    if (newCommitRes.code !== 201 || !newCommitRes.json || !newCommitRes.json.sha) {
      return { outcome: 'transient_error', error: 'Failed to create Git commit (HTTP ' + newCommitRes.code + ')' };
    }

    var patchRes = githubRequest(cfg, 'patch', '/git/refs/heads/' + encodeURIComponent(cfg.githubBranch), {
      sha: newCommitRes.json.sha,
      force: false
    });
    if (patchRes.code === 200) {
      return { outcome: 'uploaded', commitSha: newCommitRes.json.sha, attempts: attempt };
    }
    if (patchRes.code !== 422 && patchRes.code !== 409) {
      return {
        outcome: (patchRes.code >= 500 || patchRes.code === 429) ? 'transient_error' : 'rejected',
        error: 'Failed to update main ref (HTTP ' + patchRes.code + ')'
      };
    }
  }

  return { outcome: 'transient_error', error: 'Could not publish daily review after 3 non-force attempts (main moved concurrently).' };
}

/* ============================================================================
 * Unified Uplink Item Dispatcher
 * ============================================================================ */

function classifyChannelFromSubject(subject, cfg) {
  var trimmed = String(subject || '').trim();
  if (!trimmed) return null;
  var upper = trimmed.toUpperCase();
  if (upper.indexOf(cfg.rejectedSubjectPrefix.toUpperCase()) === 0) return 'already_rejected';
  if (upper.indexOf(cfg.inboxSubjectPrefix.toUpperCase()) === 0) return 'inbox';
  if (upper.indexOf(cfg.reviewSubjectPrefix.toUpperCase()) === 0) return 'review';
  return null;
}

/**
 * Validates and uploads one raw text item for a given channel ('inbox' | 'review' | 'auto').
 * Note: 'auto' is only used by Drive Inbox / Queue Doc and strictly routes based on
 * target prefix (inbox/ -> inbox validator; analysis/daily/ -> review validator).
 * For Gmail subjects, channel is locked to the subject prefix so [POSTGRAD-INBOX]
 * can NEVER write to analysis/.
 */
function processRawUplinkText(cfg, rawText, channel, sourceTag) {
  var extracted = extractJsonBlock(rawText);
  if (!extracted.ok) {
    return { outcome: 'rejected', code: extracted.code, error: extracted.error, source: sourceTag };
  }
  var parsed = parseJsonWithCurlyQuoteGuard(extracted.jsonText);
  if (!parsed.ok) {
    return { outcome: 'rejected', code: parsed.code, error: parsed.error, source: sourceTag };
  }
  var env = parsed.value;

  var effectiveChannel = channel;
  if (channel === 'auto') {
    if (isPlainObject(env) && typeof env.target === 'string' && REVIEW_TARGET_RE.test(env.target)) {
      effectiveChannel = 'review';
    } else {
      effectiveChannel = 'inbox';
    }
  }

  if (effectiveChannel === 'review') {
    var revVal = validateReviewEnvelope(env, {
      maxReportBytes: cfg.maxReviewReportBytes,
      maxContextBytes: cfg.maxReviewContextBytes
    });
    if (!revVal.ok) {
      return { outcome: 'rejected', code: revVal.code, error: revVal.error, source: sourceTag };
    }
    var revPub = publishDailyReviewToGitHub(cfg, revVal);
    return {
      outcome: revPub.outcome,
      kind: 'review',
      requestId: revVal.requestId,
      target: revVal.target,
      commitSha: revPub.commitSha || null,
      detail: revPub.detail || null,
      error: revPub.error || null,
      source: sourceTag
    };
  }

  // Default: strict inbox channel
  var inboxVal = validateInboxEnvelope(env, { maxBytes: cfg.maxInboxBytes });
  if (!inboxVal.ok) {
    return { outcome: 'rejected', code: inboxVal.code, error: inboxVal.error, source: sourceTag };
  }
  var upRes = uploadInboxToGitHub(cfg, inboxVal);
  return {
    outcome: upRes.outcome,
    kind: 'inbox',
    requestId: inboxVal.requestId,
    target: inboxVal.target,
    operation: inboxVal.payload.operation,
    commitSha: upRes.commitSha || null,
    detail: upRes.detail || null,
    error: upRes.error || null,
    source: sourceTag
  };
}

function recordUplinkOutcome(cfg, summary, result, newlySubmittedIds) {
  summary.uplink.processed += 1;
  if (result.outcome === 'uploaded') {
    if (result.kind === 'review') {
      summary.uplink.reviews_published += 1;
    } else {
      summary.uplink.uploaded += 1;
      newlySubmittedIds.push(result.requestId);
    }
    appendSyncLog(cfg, {
      ts: formatShanghaiNow(),
      action: result.kind === 'review' ? 'review_publish' : 'inbox_upload',
      status: 'uploaded',
      request_id: result.requestId,
      detail: result.target + ' (' + result.source + ')'
    });
  } else if (result.outcome === 'idempotent_skip') {
    summary.uplink.idempotent_skipped += 1;
    if (result.kind === 'inbox' && result.requestId) {
      newlySubmittedIds.push(result.requestId);
    }
    appendSyncLog(cfg, {
      ts: formatShanghaiNow(),
      action: result.kind === 'review' ? 'review_publish' : 'inbox_upload',
      status: 'idempotent_skip',
      request_id: result.requestId,
      detail: result.target + ' (' + result.source + ')'
    });
  } else if (result.outcome === 'conflict' || result.outcome === 'rejected') {
    summary.uplink.rejected += 1;
    appendSyncLog(cfg, {
      ts: formatShanghaiNow(),
      action: 'uplink_reject',
      status: result.outcome,
      request_id: result.requestId || 'unknown',
      detail: sanitizeErrorMessage(result.error, cfg.githubToken)
    });
  } else {
    summary.uplink.transient_errors += 1;
    appendSyncLog(cfg, {
      ts: formatShanghaiNow(),
      action: 'uplink_retry_later',
      status: 'transient_error',
      request_id: result.requestId || 'unknown',
      detail: sanitizeErrorMessage(result.error, cfg.githubToken)
    });
  }
}

/* ============================================================================
 * Uplink Channel 1: Gmail Drafts (Primary)
 * ============================================================================ */

function getPlainMessageBody(message) {
  var plain = '';
  try {
    plain = message.getPlainBody() || '';
  } catch (_e) {
    plain = '';
  }
  if (plain && plain.trim()) return plain;
  try {
    var html = message.getBody() || '';
    return html
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(?:p|div|li|pre)>/gi, '\n')
      .replace(/<[^>]+>/g, '')
      .replace(/&quot;/g, '"')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>');
  } catch (_e2) {
    return '';
  }
}

function buildRejectedDraftSubject(originalSubject, cfg) {
  var cleaned = String(originalSubject || '')
    .replace(/^\[POSTGRAD-INBOX\]\s*/i, '')
    .replace(/^\[POSTGRAD-REVIEW\]\s*/i, '')
    .replace(/^\[POSTGRAD-REJECTED\]\s*/i, '')
    .trim();
  return cfg.rejectedSubjectPrefix + (cleaned ? ' ' + cleaned : '');
}

function buildRejectedDraftBody(reason, originalBody) {
  return [
    '=== POSTGRAD BRIDGE REJECTED ===',
    'Time: ' + formatShanghaiNow(),
    'Reason: ' + reason,
    'Action: Fix the JSON/schema issue below, remove this header, and change the subject back to [POSTGRAD-INBOX] (or [POSTGRAD-REVIEW]) to retry.',
    '================================',
    '',
    originalBody || ''
  ].join('\n');
}

function processGmailDrafts(cfg, summary, newlySubmittedIds) {
  var changed = false;
  var drafts = GmailApp.getDrafts() || [];
  for (var i = 0; i < drafts.length; i++) {
    var draft = drafts[i];
    var msg = draft.getMessage();
    var subject = msg.getSubject() || '';
    var channel = classifyChannelFromSubject(subject, cfg);
    if (!channel || channel === 'already_rejected') continue;

    changed = true;
    var body = getPlainMessageBody(msg);
    var result = processRawUplinkText(cfg, body, channel, 'gmail_draft');
    recordUplinkOutcome(cfg, summary, result, newlySubmittedIds);

    if (result.outcome === 'uploaded' || result.outcome === 'idempotent_skip') {
      draft.deleteDraft();
    } else if (result.outcome === 'rejected' || result.outcome === 'conflict') {
      var safeReason = sanitizeErrorMessage(result.error, cfg.githubToken);
      var newSubject = buildRejectedDraftSubject(subject, cfg);
      var newBody = buildRejectedDraftBody(safeReason, body);
      draft.update(msg.getTo() || '', newSubject, newBody);
    }
    // transient_error: leave draft untouched for next 5-min retry
  }
  return { changed: changed };
}

/* ============================================================================
 * Uplink Channel 2: Sent / Received Gmail Messages (Compatible)
 * ============================================================================ */

function getOrCreateGmailLabel(name) {
  var existing = GmailApp.getUserLabelByName(name);
  if (existing) return existing;
  return GmailApp.createLabel(name);
}

function processGmailMessages(cfg, summary, newlySubmittedIds) {
  var changed = false;
  var query = '(subject:"' + cfg.inboxSubjectPrefix + '" OR subject:"' + cfg.reviewSubjectPrefix + '") ' +
    '-label:"' + cfg.gmailLabelProcessed + '" -label:"' + cfg.gmailLabelRejected + '"';
  var threads = GmailApp.search(query, 0, 20) || [];
  if (threads.length === 0) return { changed: false };

  var processedLabel = null;
  var rejectedLabel = null;

  for (var i = 0; i < threads.length; i++) {
    var thread = threads[i];
    var messages = thread.getMessages() || [];
    var threadHasNonDraft = false;
    var threadFailed = false;
    var threadTransient = false;

    for (var j = 0; j < messages.length; j++) {
      var msg = messages[j];
      if (typeof msg.isDraft === 'function' && msg.isDraft()) continue;
      var subject = msg.getSubject() || '';
      var channel = classifyChannelFromSubject(subject, cfg);
      if (!channel || channel === 'already_rejected') continue;

      threadHasNonDraft = true;
      changed = true;
      var body = getPlainMessageBody(msg);
      var result = processRawUplinkText(cfg, body, channel, 'gmail_message');
      recordUplinkOutcome(cfg, summary, result, newlySubmittedIds);

      if (result.outcome === 'rejected' || result.outcome === 'conflict') {
        threadFailed = true;
      } else if (result.outcome === 'transient_error') {
        threadTransient = true;
      }
    }

    if (threadHasNonDraft && !threadTransient) {
      if (threadFailed) {
        rejectedLabel = rejectedLabel || getOrCreateGmailLabel(cfg.gmailLabelRejected);
        thread.addLabel(rejectedLabel);
      } else {
        processedLabel = processedLabel || getOrCreateGmailLabel(cfg.gmailLabelProcessed);
        thread.addLabel(processedLabel);
      }
    }
  }
  return { changed: changed };
}

/* ============================================================================
 * Uplink Channel 3: Drive Folder Postgrad-Inbox/ (Compatible)
 * ============================================================================ */

function readDriveFileAsText(file) {
  var mime = file.getMimeType();
  if (mime === 'application/vnd.google-apps.document') {
    var doc = DocumentApp.openById(file.getId());
    return doc.getBody().getText();
  }
  return file.getBlob().getDataAsString('UTF-8');
}

function processDriveInboxFolder(cfg, resources, summary, newlySubmittedIds) {
  var changed = false;
  var inboxFolder = DriveApp.getFolderById(resources.inboxFolderId);
  var processedFolder = DriveApp.getFolderById(resources.processedFolderId);
  var rejectedFolder = DriveApp.getFolderById(resources.rejectedFolderId);

  var files = inboxFolder.getFiles();
  while (files.hasNext()) {
    var file = files.next();
    if (typeof file.isTrashed === 'function' && file.isTrashed()) continue;
    changed = true;
    var rawText = '';
    try {
      rawText = readDriveFileAsText(file);
    } catch (readErr) {
      var errResult = {
        outcome: 'rejected',
        error: 'Unable to read Drive inbox file ' + file.getName() + ': ' + sanitizeErrorMessage(readErr, cfg.githubToken),
        source: 'drive_inbox:' + file.getName()
      };
      recordUplinkOutcome(cfg, summary, errResult, newlySubmittedIds);
      file.moveTo(rejectedFolder);
      continue;
    }

    var result = processRawUplinkText(cfg, rawText, 'auto', 'drive_inbox:' + file.getName());
    recordUplinkOutcome(cfg, summary, result, newlySubmittedIds);

    if (result.outcome === 'uploaded' || result.outcome === 'idempotent_skip') {
      file.moveTo(processedFolder);
    } else if (result.outcome === 'rejected' || result.outcome === 'conflict') {
      file.moveTo(rejectedFolder);
    }
    // transient_error: keep in Postgrad-Inbox/ for next cycle
  }
  return { changed: changed };
}

/* ============================================================================
 * Uplink Channel 4: Drive Fixed Queue Doc Postgrad-Inbox-Queue (Compatible)
 * ============================================================================ */

function stripQueueHeaderLines(text) {
  var lines = String(text || '').replace(/^\uFEFF/, '').split(/\r?\n/);
  var kept = [];
  for (var i = 0; i < lines.length; i++) {
    var trimmed = lines[i].trim();
    if (trimmed.indexOf('#') === 0 || trimmed.indexOf('//') === 0) continue;
    kept.push(lines[i]);
  }
  return kept.join('\n').trim();
}

function processDriveQueueDoc(cfg, resources, summary, newlySubmittedIds) {
  var file = DriveApp.getFileById(resources.queueDocId);
  var currentUpdatedMs = String(file.getLastUpdated().getTime());
  var lastSeenMs = getProp('QUEUE_DOC_LAST_UPDATED_MS');

  // Fast-path: never open the queue doc if unchanged since last check
  if (lastSeenMs && lastSeenMs === currentUpdatedMs) {
    return { changed: false, skippedUnchanged: true };
  }

  var rawText = readDriveFileAsText(file);
  var bodyWithoutComments = stripQueueHeaderLines(rawText);
  if (!bodyWithoutComments) {
    setProp('QUEUE_DOC_LAST_UPDATED_MS', currentUpdatedMs);
    return { changed: false, skippedEmpty: true };
  }

  var chunks = bodyWithoutComments.split(/^\s*===POSTGRAD-ITEM===\s*$/m);
  var remainingBlocks = [];
  var anyProcessed = false;

  for (var i = 0; i < chunks.length; i++) {
    var chunk = chunks[i].trim();
    if (!chunk) continue;
    if (chunk.indexOf('[POSTGRAD-REJECTED]') === 0) {
      remainingBlocks.push(chunk);
      continue;
    }

    anyProcessed = true;
    var result = processRawUplinkText(cfg, chunk, 'auto', 'drive_queue');
    recordUplinkOutcome(cfg, summary, result, newlySubmittedIds);

    if (result.outcome === 'rejected' || result.outcome === 'conflict') {
      remainingBlocks.push('[POSTGRAD-REJECTED] ' + sanitizeErrorMessage(result.error, cfg.githubToken) + '\n' + chunk);
    } else if (result.outcome === 'transient_error') {
      remainingBlocks.push(chunk);
    }
  }

  if (anyProcessed) {
    var nextDocText = QUEUE_DOC_HEADER + (remainingBlocks.length > 0 ? '\n' + remainingBlocks.join('\n\n===POSTGRAD-ITEM===\n\n') + '\n' : '');
    writeDocPreservingId(resources.queueDocId, nextDocText);
    var updatedAfterWriteMs = String(DriveApp.getFileById(resources.queueDocId).getLastUpdated().getTime());
    setProp('QUEUE_DOC_LAST_UPDATED_MS', updatedAfterWriteMs);
    return { changed: true };
  }

  setProp('QUEUE_DOC_LAST_UPDATED_MS', currentUpdatedMs);
  return { changed: false };
}

/* ============================================================================
 * Outbox Receipt Polling & Pending Follow-up
 * ============================================================================ */

function loadPendingOutboxIds() {
  var raw = getProp('PENDING_OUTBOX_IDS');
  if (!raw) return [];
  try {
    var arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (_e) {
    return [];
  }
}

function savePendingOutboxIds(ids) {
  // Cap to 30 IDs to stay well under ScriptProperties limits
  var unique = [];
  var seen = {};
  for (var i = 0; i < ids.length; i++) {
    if (ids[i] && !seen[ids[i]]) {
      seen[ids[i]] = true;
      unique.push(ids[i]);
    }
  }
  if (unique.length > 30) unique = unique.slice(unique.length - 30);
  setProp('PENDING_OUTBOX_IDS', JSON.stringify(unique));
}

function loadRecentReceipts() {
  var raw = getProp('RECENT_RECEIPTS_JSON');
  if (!raw) return [];
  try {
    var arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (_e) {
    return [];
  }
}

function saveRecentReceipt(receipt) {
  var list = loadRecentReceipts();
  var compact = {
    request_id: receipt.request_id,
    operation: receipt.operation,
    status: receipt.status,
    processed_at: receipt.processed_at || formatShanghaiNow(),
    record_id: receipt.result && receipt.result.record_id ? receipt.result.record_id : null,
    error: receipt.error && receipt.error.message ? String(receipt.error.message).slice(0, 160) : null
  };
  var filtered = [compact];
  for (var i = 0; i < list.length; i++) {
    if (list[i] && list[i].request_id !== compact.request_id) {
      filtered.push(list[i]);
    }
  }
  if (filtered.length > DEFAULT_CONFIG.MAX_RECENT_RECEIPTS) {
    filtered = filtered.slice(0, DEFAULT_CONFIG.MAX_RECENT_RECEIPTS);
  }
  setProp('RECENT_RECEIPTS_JSON', JSON.stringify(filtered));
}

function checkOutboxOnce(cfg, requestId) {
  var res = githubGetContent(cfg, 'outbox/' + requestId + '.json');
  if (res.status !== 'found') return null;
  try {
    var receipt = JSON.parse(res.content);
    if (receipt && receipt.request_id === requestId) return receipt;
    return null;
  } catch (_e) {
    return null;
  }
}

function pollOutboxReceipts(cfg, newlySubmittedIds) {
  var priorPending = loadPendingOutboxIds();
  var combined = [];
  var seen = {};
  var all = priorPending.concat(newlySubmittedIds || []);
  for (var i = 0; i < all.length; i++) {
    if (all[i] && !seen[all[i]]) {
      seen[all[i]] = true;
      combined.push(all[i]);
    }
  }
  if (combined.length === 0) return { resolved: [], stillPending: [], changed: false };

  var resolved = [];
  var stillPending = combined.slice();
  var hasNewUploads = newlySubmittedIds && newlySubmittedIds.length > 0;
  var deadline = Date.now() + (hasNewUploads ? cfg.outboxPollMaxMs : 0);

  // If we just uploaded, wait briefly for GitHub Actions to start & finish
  if (hasNewUploads && cfg.outboxPollInitialMs > 0) {
    Utilities.sleep(cfg.outboxPollInitialMs);
  }

  while (stillPending.length > 0) {
    var nextPending = [];
    for (var j = 0; j < stillPending.length; j++) {
      var rid = stillPending[j];
      var receipt = checkOutboxOnce(cfg, rid);
      if (receipt) {
        resolved.push(receipt);
        saveRecentReceipt(receipt);
        appendSyncLog(cfg, {
          ts: formatShanghaiNow(),
          action: 'outbox_receipt',
          status: receipt.status,
          request_id: rid,
          detail: receipt.operation + (receipt.error && receipt.error.message ? ' | ' + receipt.error.message : '')
        });
      } else {
        nextPending.push(rid);
      }
    }
    stillPending = nextPending;
    if (stillPending.length === 0 || Date.now() >= deadline) break;
    Utilities.sleep(cfg.outboxPollIntervalMs);
  }

  savePendingOutboxIds(stillPending);
  return {
    resolved: resolved,
    stillPending: stillPending,
    changed: resolved.length > 0 || hasNewUploads
  };
}

/* ============================================================================
 * Downlink Sync (GitHub main -> Fixed Google Docs via Drive v3 In-Place Update)
 * ============================================================================ */

function writeDocPreservingId(docId, text) {
  var safeText = (typeof text === 'string' && text.length > 0) ? text : '\n';
  if (typeof Drive !== 'undefined' && Drive && Drive.Files && typeof Drive.Files.update === 'function') {
    var blob = Utilities.newBlob(safeText, 'text/plain; charset=utf-8');
    Drive.Files.update(
      { mimeType: 'application/vnd.google-apps.document' },
      docId,
      blob
    );
    return { method: 'drive_v3', bytes: blob.getBytes().length };
  }
  // Fallback only when Drive v3 Advanced Service is not available
  var doc = DocumentApp.openById(docId);
  doc.getBody().setText(safeText);
  doc.saveAndClose();
  return { method: 'document_app_fallback', bytes: utf8ByteLength(safeText) };
}

function githubGetHeadSha(cfg) {
  var res = githubRequest(cfg, 'get', '/git/ref/heads/' + encodeURIComponent(cfg.githubBranch), null);
  if (res.code !== 200 || !res.json || !res.json.object || !res.json.object.sha) {
    throw new Error('Failed to fetch GitHub HEAD ref (HTTP ' + res.code + ')');
  }
  return res.json.object.sha;
}

function githubGetRecursiveTree(cfg, headSha) {
  var res = githubRequest(cfg, 'get', '/git/trees/' + headSha + '?recursive=1', null);
  if (res.code !== 200 || !res.json || !Array.isArray(res.json.tree)) {
    throw new Error('Failed to fetch GitHub tree (HTTP ' + res.code + ')');
  }
  var map = {};
  for (var i = 0; i < res.json.tree.length; i++) {
    var item = res.json.tree[i];
    if (item && item.type === 'blob' && item.path && item.sha) {
      map[item.path] = item.sha;
    }
  }
  return map;
}

function githubGetBlobText(cfg, blobSha) {
  var res = githubRequest(cfg, 'get', '/git/blobs/' + blobSha, null);
  if (res.code !== 200 || !res.json || typeof res.json.content !== 'string') {
    throw new Error('Failed to fetch GitHub blob ' + shortSha(blobSha) + ' (HTTP ' + res.code + ')');
  }
  return decodeBase64Utf8(res.json.content);
}

function computeDocFingerprint(paths, treeMap) {
  var parts = [];
  for (var i = 0; i < paths.length; i++) {
    var p = paths[i];
    parts.push(p + ':' + (treeMap[p] || 'missing'));
  }
  return parts.join('|');
}

function selectDynamicStatePaths(treeMap, maxOutbox) {
  var paths = STATE_STATIC_PATHS.slice();
  var allPaths = Object.keys(treeMap);

  var dailyReports = [];
  var outboxFiles = [];
  for (var i = 0; i < allPaths.length; i++) {
    var p = allPaths[i];
    if (REVIEW_TARGET_RE.test(p)) {
      dailyReports.push(p);
    } else if (/^outbox\/[^/]+\.json$/.test(p)) {
      outboxFiles.push(p);
    }
  }
  dailyReports.sort();
  if (dailyReports.length > 0) {
    paths.splice(1, 0, dailyReports[dailyReports.length - 1]);
  }
  outboxFiles.sort();
  outboxFiles.reverse();
  var topOutbox = outboxFiles.slice(0, maxOutbox || DEFAULT_CONFIG.LATEST_OUTBOX_IN_STATE_DOC);
  for (var j = 0; j < topOutbox.length; j++) {
    paths.push(topOutbox[j]);
  }
  return paths;
}

function renderMirroredBundle(title, headSha, syncedAt, sections, repoSlug) {
  var srcRepo = repoSlug || 'private-vault';
  var out = [
    '# ' + title,
    'Mirror Source: ' + srcRepo + '@' + shortSha(headSha) + ' (' + headSha + ')',
    'Synced At (Asia/Shanghai): ' + syncedAt,
    'Read-Only Mirror: Do NOT edit this Doc manually; submit changes via Gmail Draft [POSTGRAD-INBOX] or [POSTGRAD-REVIEW].',
    ''
  ];
  for (var i = 0; i < sections.length; i++) {
    out.push('================================================================================');
    out.push('FILE: ' + sections[i].path + ' (sha: ' + shortSha(sections[i].sha) + ')');
    out.push('================================================================================');
    out.push(sections[i].content.replace(/\r\n/g, '\n').trimEnd());
    out.push('');
  }
  return out.join('\n');
}

function summarizeJsonlLedger(jsonlText, idField) {
  var lines = String(jsonlText || '').replace(/\r\n/g, '\n').split('\n');
  var count = 0;
  var lastId = 'none';
  var indexedLines = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim();
    if (!line) continue;
    count += 1;
    try {
      var obj = JSON.parse(line);
      if (obj && obj[idField]) lastId = obj[idField];
    } catch (_e) {
      // keep raw line even if unparseable
    }
    indexedLines.push(line);
  }
  return { count: count, lastId: lastId, lines: indexedLines };
}

function renderLedgersDoc(headSha, syncedAt, recordsText, recordsSha, eventsText, eventsSha, repoSlug) {
  var srcRepo = repoSlug || 'private-vault';
  var rec = summarizeJsonlLedger(recordsText, 'record_id');
  var ev = summarizeJsonlLedger(eventsText, 'event_id');

  var out = [
    '# Postgrad-3-学习账本原始记录（只读镜像）',
    'Mirror Source: ' + srcRepo + '@' + shortSha(headSha) + ' (' + headSha + ')',
    'Synced At (Asia/Shanghai): ' + syncedAt,
    'study_record_count: ' + rec.count,
    'last_record_id: ' + rec.lastId,
    'formal_event_count: ' + ev.count,
    'last_event_id: ' + ev.lastId,
    '',
    '================================================================================',
    'FILE: records/study_records.jsonl (sha: ' + shortSha(recordsSha) + ', lines: ' + rec.count + ')',
    '================================================================================'
  ];
  for (var i = 0; i < rec.lines.length; i++) {
    var rTag = 'R' + (i + 1 < 10 ? '0' + (i + 1) : String(i + 1));
    out.push('[' + rTag + '] ' + rec.lines[i]);
  }
  out.push('');
  out.push('================================================================================');
  out.push('FILE: events/learning_events.jsonl (sha: ' + shortSha(eventsSha) + ', lines: ' + ev.count + ')');
  out.push('================================================================================');
  for (var j = 0; j < ev.lines.length; j++) {
    var eTag = 'E' + (j + 1 < 10 ? '0' + (j + 1) : String(j + 1));
    out.push('[' + eTag + '] ' + ev.lines[j]);
  }
  out.push('');
  return out.join('\n');
}

function syncDownlinkInternal(cfg, resources, force) {
  var headSha = githubGetHeadSha(cfg);
  var lastHeadSha = getProp('LAST_SYNCED_HEAD_SHA');

  if (!force && lastHeadSha && lastHeadSha === headSha) {
    return { skipped: true, reason: 'head_unchanged', headSha: headSha, updatedDocs: [] };
  }

  var treeMap = githubGetRecursiveTree(cfg, headSha);
  var syncedAt = formatShanghaiNow();
  var updatedDocs = [];
  var writeMethods = {};

  // 1. Postgrad-1-协议与学科说明
  var fpProtocols = computeDocFingerprint(PROTOCOL_DOC_PATHS, treeMap);
  if (force || getProp('FP_PROTOCOLS') !== fpProtocols) {
    var protoSections = [];
    for (var i = 0; i < PROTOCOL_DOC_PATHS.length; i++) {
      var pPath = PROTOCOL_DOC_PATHS[i];
      if (!treeMap[pPath]) continue;
      protoSections.push({ path: pPath, sha: treeMap[pPath], content: githubGetBlobText(cfg, treeMap[pPath]) });
    }
    var repoSlug = cfg.githubOwner + '/' + cfg.githubRepo;
    var protoText = renderMirroredBundle(cfg.docNameProtocols + '（只读镜像）', headSha, syncedAt, protoSections, repoSlug);
    var res1 = writeDocPreservingId(resources.protocolsDocId, protoText);
    setProp('FP_PROTOCOLS', fpProtocols);
    updatedDocs.push(cfg.docNameProtocols);
    writeMethods[cfg.docNameProtocols] = res1.method;
  }

  // 2. Postgrad-2-学习画像与核心状态
  var statePaths = selectDynamicStatePaths(treeMap, DEFAULT_CONFIG.LATEST_OUTBOX_IN_STATE_DOC);
  var fpState = computeDocFingerprint(statePaths, treeMap);
  if (force || getProp('FP_STATE') !== fpState) {
    var stateSections = [];
    for (var j = 0; j < statePaths.length; j++) {
      var sPath = statePaths[j];
      if (!treeMap[sPath]) continue;
      stateSections.push({ path: sPath, sha: treeMap[sPath], content: githubGetBlobText(cfg, treeMap[sPath]) });
    }
    var stateText = renderMirroredBundle(cfg.docNameState + '（只读镜像）', headSha, syncedAt, stateSections, cfg.githubOwner + '/' + cfg.githubRepo);
    var res2 = writeDocPreservingId(resources.stateDocId, stateText);
    setProp('FP_STATE', fpState);
    updatedDocs.push(cfg.docNameState);
    writeMethods[cfg.docNameState] = res2.method;
  }

  // 3. Postgrad-3-学习账本原始记录
  var fpLedgers = computeDocFingerprint(LEDGER_DOC_PATHS, treeMap);
  if (force || getProp('FP_LEDGERS') !== fpLedgers) {
    var recSha = treeMap['records/study_records.jsonl'] || '';
    var evSha = treeMap['events/learning_events.jsonl'] || '';
    var recText = recSha ? githubGetBlobText(cfg, recSha) : '';
    var evText = evSha ? githubGetBlobText(cfg, evSha) : '';
    var ledgersText = renderLedgersDoc(headSha, syncedAt, recText, recSha, evText, evSha, cfg.githubOwner + '/' + cfg.githubRepo);
    var res3 = writeDocPreservingId(resources.ledgersDocId, ledgersText);
    setProp('FP_LEDGERS', fpLedgers);
    updatedDocs.push(cfg.docNameLedgers);
    writeMethods[cfg.docNameLedgers] = res3.method;
  }

  setProp('LAST_SYNCED_HEAD_SHA', headSha);
  setProp('LAST_SYNCED_AT', syncedAt);

  return {
    skipped: false,
    headSha: headSha,
    syncedAt: syncedAt,
    updatedDocs: updatedDocs,
    writeMethods: writeMethods
  };
}

/* ============================================================================
 * Sync Log Doc Management (Postgrad-4-同步日志与回执)
 * ============================================================================ */

function loadSyncLogEntries() {
  var raw = getProp('SYNC_LOG_JSON');
  if (!raw) return [];
  try {
    var arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (_e) {
    return [];
  }
}

function appendSyncLog(cfg, entry) {
  var list = loadSyncLogEntries();
  var compact = {
    ts: entry.ts || formatShanghaiNow(),
    action: String(entry.action || 'event').slice(0, 32),
    status: String(entry.status || 'info').slice(0, 32),
    request_id: entry.request_id ? String(entry.request_id).slice(0, 96) : '',
    detail: sanitizeErrorMessage(entry.detail || '', cfg.githubToken).slice(0, 160)
  };
  list.unshift(compact);
  if (list.length > DEFAULT_CONFIG.MAX_SYNC_LOG_ENTRIES) {
    list = list.slice(0, DEFAULT_CONFIG.MAX_SYNC_LOG_ENTRIES);
  }
  // Guard ScriptProperties 9 KB per-key limit
  var json = JSON.stringify(list);
  while (utf8ByteLength(json) > 8000 && list.length > 5) {
    list.pop();
    json = JSON.stringify(list);
  }
  setProp('SYNC_LOG_JSON', json);
}

function refreshSyncLogDoc(cfg, resources) {
  var entries = loadSyncLogEntries();
  var receipts = loadRecentReceipts();
  var pending = loadPendingOutboxIds();
  var driveV3Ready = (typeof Drive !== 'undefined' && Drive && Drive.Files && typeof Drive.Files.update === 'function');

  var lines = [
    '# ' + cfg.docNameSyncLog,
    'Bridge Version: ' + BRIDGE_VERSION,
    'Last Updated (Asia/Shanghai): ' + formatShanghaiNow(),
    'GitHub Repository: ' + cfg.githubOwner + '/' + cfg.githubRepo + '@' + cfg.githubBranch,
    'Last Synced HEAD: ' + (getProp('LAST_SYNCED_HEAD_SHA') || 'not_yet_synced'),
    'Last Synced At: ' + (getProp('LAST_SYNCED_AT') || 'never'),
    'Drive v3 Fast Update: ' + (driveV3Ready ? 'enabled' : 'fallback_document_app'),
    'Pending Outbox IDs (' + pending.length + '): ' + (pending.length > 0 ? pending.join(', ') : 'none'),
    '',
    '## 最近已核验 Outbox 回执（最新在前）',
    ''
  ];

  if (receipts.length === 0) {
    lines.push('- 暂无本次桥接轮询到的新回执（历史回执见 Postgrad-2-学习画像与核心状态）。');
  } else {
    for (var i = 0; i < receipts.length; i++) {
      var r = receipts[i];
      var extra = r.record_id ? (' | record_id=' + r.record_id) : (r.error ? (' | error=' + r.error) : '');
      lines.push('- [' + r.status + '] ' + r.request_id + ' (' + r.operation + ') @ ' + r.processed_at + extra);
    }
  }

  lines.push('');
  lines.push('## 最近同步事件日志（最新在前）');
  lines.push('');

  if (entries.length === 0) {
    lines.push('- 暂无同步事件。');
  } else {
    for (var j = 0; j < entries.length; j++) {
      var e = entries[j];
      lines.push('- [' + e.ts + '] ' + e.action + ' => ' + e.status +
        (e.request_id ? (' | ' + e.request_id) : '') +
        (e.detail ? (' | ' + e.detail) : ''));
    }
  }
  lines.push('');

  writeDocPreservingId(resources.syncLogDocId, lines.join('\n'));
}

/* ============================================================================
 * Google Drive Resource Discovery / Bootstrap (Preserves Stable File IDs)
 * ============================================================================ */

function findOrCreateFolder(parentFolder, folderName, propKey) {
  var cachedId = getProp(propKey);
  if (cachedId) {
    try {
      var cached = DriveApp.getFolderById(cachedId);
      if (!cached.isTrashed()) return cached;
    } catch (_e) {
      // Cache stale; fall through to name search
    }
  }
  var iter = parentFolder ? parentFolder.getFoldersByName(folderName) : DriveApp.getRootFolder().getFoldersByName(folderName);
  while (iter.hasNext()) {
    var existing = iter.next();
    if (!existing.isTrashed()) {
      setProp(propKey, existing.getId());
      return existing;
    }
  }
  var created = parentFolder ? parentFolder.createFolder(folderName) : DriveApp.createFolder(folderName);
  setProp(propKey, created.getId());
  return created;
}

function findOrCreateDocInFolder(folder, docName, propKey, initialText) {
  var cachedId = getProp(propKey);
  if (cachedId) {
    try {
      var cached = DriveApp.getFileById(cachedId);
      if (!cached.isTrashed()) return cached.getId();
    } catch (_e) {
      // Cache stale; fall through to name search
    }
  }
  var iter = folder.getFilesByName(docName);
  while (iter.hasNext()) {
    var existing = iter.next();
    if (!existing.isTrashed() && existing.getMimeType() === 'application/vnd.google-apps.document') {
      setProp(propKey, existing.getId());
      return existing.getId();
    }
  }
  var doc = DocumentApp.create(docName);
  var docId = doc.getId();
  if (initialText) {
    doc.getBody().setText(initialText);
    doc.saveAndClose();
  }
  DriveApp.getFileById(docId).moveTo(folder);
  setProp(propKey, docId);
  return docId;
}

function ensureDriveResources(cfg) {
  var cloudFolder = findOrCreateFolder(null, cfg.cloudFolderName, 'CLOUD_FOLDER_ID');
  var inboxFolder = findOrCreateFolder(cloudFolder, cfg.inboxFolderName, 'INBOX_FOLDER_ID');
  var processedFolder = findOrCreateFolder(cloudFolder, cfg.processedFolderName, 'PROCESSED_FOLDER_ID');
  var rejectedFolder = findOrCreateFolder(cloudFolder, cfg.rejectedFolderName, 'REJECTED_FOLDER_ID');

  var protocolsDocId = findOrCreateDocInFolder(cloudFolder, cfg.docNameProtocols, 'DOC_ID_PROTOCOLS', '# ' + cfg.docNameProtocols + '\nPending initial sync...\n');
  var stateDocId = findOrCreateDocInFolder(cloudFolder, cfg.docNameState, 'DOC_ID_STATE', '# ' + cfg.docNameState + '\nPending initial sync...\n');
  var ledgersDocId = findOrCreateDocInFolder(cloudFolder, cfg.docNameLedgers, 'DOC_ID_LEDGERS', '# ' + cfg.docNameLedgers + '\nPending initial sync...\n');
  var syncLogDocId = findOrCreateDocInFolder(cloudFolder, cfg.docNameSyncLog, 'DOC_ID_SYNCLOG', '# ' + cfg.docNameSyncLog + '\nInitializing...\n');
  var queueDocId = findOrCreateDocInFolder(cloudFolder, cfg.docNameQueue, 'DOC_ID_QUEUE', QUEUE_DOC_HEADER);

  return {
    cloudFolderId: cloudFolder.getId(),
    inboxFolderId: inboxFolder.getId(),
    processedFolderId: processedFolder.getId(),
    rejectedFolderId: rejectedFolder.getId(),
    protocolsDocId: protocolsDocId,
    stateDocId: stateDocId,
    ledgersDocId: ledgersDocId,
    syncLogDocId: syncLogDocId,
    queueDocId: queueDocId
  };
}

/* ============================================================================
 * Node.js Test Export Hook (Ignored in Apps Script V8 Runtime)
 * ============================================================================ */

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    BRIDGE_VERSION: BRIDGE_VERSION,
    DEFAULT_CONFIG: DEFAULT_CONFIG,
    PROTOCOL_DOC_PATHS: PROTOCOL_DOC_PATHS,
    STATE_STATIC_PATHS: STATE_STATIC_PATHS,
    LEDGER_DOC_PATHS: LEDGER_DOC_PATHS,
    QUEUE_DOC_HEADER: QUEUE_DOC_HEADER,
    setupBridge: setupBridge,
    installTrigger: installTrigger,
    runBridgeCycle: runBridgeCycle,
    forceSyncDownlink: forceSyncDownlink,
    syncUplinkOnly: syncUplinkOnly,
    extractJsonBlock: extractJsonBlock,
    parseJsonWithCurlyQuoteGuard: parseJsonWithCurlyQuoteGuard,
    validateInboxEnvelope: validateInboxEnvelope,
    validateReviewEnvelope: validateReviewEnvelope,
    validateCoreMobileRequest: validateCoreMobileRequest,
    parseSimpleFrontmatter: parseSimpleFrontmatter,
    canonicalJson: canonicalJson,
    isValidIsoDate: isValidIsoDate,
    isValidIsoDateTimeWithTz: isValidIsoDateTimeWithTz,
    utf8ByteLength: utf8ByteLength,
    writeDocPreservingId: writeDocPreservingId,
    uploadInboxToGitHub: uploadInboxToGitHub,
    publishDailyReviewToGitHub: publishDailyReviewToGitHub,
    processRawUplinkText: processRawUplinkText,
    syncDownlinkInternal: syncDownlinkInternal,
    renderMirroredBundle: renderMirroredBundle,
    renderLedgersDoc: renderLedgersDoc,
    summarizeJsonlLedger: summarizeJsonlLedger
  };
}
