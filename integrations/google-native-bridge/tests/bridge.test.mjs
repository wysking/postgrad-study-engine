import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CODE_PATH = path.resolve(__dirname, '../Code.gs');
const MANIFEST_PATH = path.resolve(__dirname, '../appsscript.json');
const CODE_SOURCE = fs.readFileSync(CODE_PATH, 'utf8');

function b64(str) {
  return Buffer.from(str, 'utf8').toString('base64');
}

function unb64(str) {
  return Buffer.from(String(str).replace(/\s+/g, ''), 'base64').toString('utf8');
}

/**
 * Creates a full in-memory Apps Script V8 sandbox for testing Code.gs end-to-end.
 */
function createGasHarness(opts = {}) {
  const props = {
    GITHUB_TOKEN: 'github_pat_test_token_secret_12345',
    GITHUB_OWNER: 'example-learner',
    GITHUB_REPO: 'example-study-vault',
    OUTBOX_POLL_INITIAL_MS: '1',
    OUTBOX_POLL_INTERVAL_MS: '1',
    OUTBOX_POLL_MAX_MS: '5',
    ...(opts.props || {})
  };

  const lockState = {
    busy: Boolean(opts.lockBusy),
    acquiredCount: 0,
    releasedCount: 0
  };

  // In-memory Drive store
  let nextId = 100;
  const folders = new Map();
  const files = new Map();
  const driveV3Updates = [];
  const docAppOpens = [];
  const docAppSetTexts = [];
  const triggers = [];
  const logs = [];

  function makeFolder(id, name, parentId = null) {
    const f = {
      id,
      name,
      parentId,
      trashed: false,
      getId: () => f.id,
      getName: () => f.name,
      isTrashed: () => f.trashed,
      getFoldersByName: (targetName) => {
        const list = [...folders.values()].filter(
          (x) => x.parentId === f.id && x.name === targetName && !x.trashed
        );
        let idx = 0;
        return { hasNext: () => idx < list.length, next: () => list[idx++] };
      },
      createFolder: (childName) => {
        const child = makeFolder('fld_' + (++nextId), childName, f.id);
        return child;
      },
      getFilesByName: (targetName) => {
        const list = [...files.values()].filter(
          (x) => x.parentId === f.id && x.name === targetName && !x.trashed
        );
        let idx = 0;
        return { hasNext: () => idx < list.length, next: () => list[idx++] };
      },
      getFiles: () => {
        const list = [...files.values()].filter((x) => x.parentId === f.id && !x.trashed);
        let idx = 0;
        return { hasNext: () => idx < list.length, next: () => list[idx++] };
      }
    };
    folders.set(id, f);
    return f;
  }

  function makeFile(id, name, mimeType, content = '', parentId = 'root') {
    const file = {
      id,
      name,
      mimeType,
      content,
      parentId,
      trashed: false,
      updatedMs: Date.now(),
      getId: () => file.id,
      getName: () => file.name,
      getMimeType: () => file.mimeType,
      isTrashed: () => file.trashed,
      getLastUpdated: () => new Date(file.updatedMs),
      moveTo: (targetFolder) => {
        file.parentId = targetFolder.getId();
        return file;
      },
      getBlob: () => ({
        getDataAsString: () => file.content,
        getBytes: () => Buffer.from(file.content, 'utf8')
      })
    };
    files.set(id, file);
    return file;
  }

  const rootFolder = makeFolder('root', 'My Drive', null);

  // In-memory Gmail store
  const drafts = [];
  const threads = [];
  const labels = new Map();

  function addDraft({ subject, body, to = '' }) {
    const d = {
      deleted: false,
      subject,
      body,
      to,
      updatedCount: 0,
      getMessage: () => ({
        getSubject: () => d.subject,
        getPlainBody: () => d.body,
        getBody: () => d.body,
        getTo: () => d.to,
        isDraft: () => true
      }),
      deleteDraft: () => {
        d.deleted = true;
      },
      update: (newTo, newSubject, newBody) => {
        d.to = newTo;
        d.subject = newSubject;
        d.body = newBody;
        d.updatedCount += 1;
      }
    };
    drafts.push(d);
    return d;
  }

  function addThread({ subject, body, isDraft = false }) {
    const t = {
      labels: new Set(),
      messages: [
        {
          getSubject: () => subject,
          getPlainBody: () => body,
          getBody: () => body,
          isDraft: () => isDraft
        }
      ],
      getMessages: () => t.messages,
      addLabel: (labelObj) => {
        t.labels.add(labelObj.name);
      }
    };
    threads.push(t);
    return t;
  }

  // In-memory GitHub REST mock
  const ghCalls = [];
  const ghHandler = opts.githubHandler || (() => ({ code: 404, body: { message: 'Not Found' } }));

  const sandbox = {
    console,
    Date,
    JSON,
    Math,
    Number,
    String,
    Boolean,
    Array,
    Object,
    RegExp,
    Error,
    isFinite,
    encodeURIComponent,
    decodeURIComponent,
    module: { exports: {} },
    Logger: {
      log: (m) => logs.push(String(m))
    },
    PropertiesService: {
      getScriptProperties: () => ({
        getProperty: (k) => (Object.prototype.hasOwnProperty.call(props, k) ? props[k] : null),
        setProperty: (k, v) => {
          props[k] = String(v);
        },
        getProperties: () => ({ ...props })
      })
    },
    LockService: {
      getScriptLock: () => ({
        tryLock: () => {
          if (lockState.busy) return false;
          lockState.acquiredCount += 1;
          return true;
        },
        releaseLock: () => {
          lockState.releasedCount += 1;
        }
      })
    },
    Utilities: {
      newBlob: (data, contentType) => {
        const buf = Buffer.isBuffer(data)
          ? data
          : Array.isArray(data)
            ? Buffer.from(data)
            : Buffer.from(String(data), 'utf8');
        return {
          contentType: contentType || 'application/octet-stream',
          getBytes: () => [...buf],
          getDataAsString: () => buf.toString('utf8')
        };
      },
      base64Encode: (bytes) => Buffer.from(bytes).toString('base64'),
      base64Decode: (str) => [...Buffer.from(String(str), 'base64')],
      formatDate: (date) => {
        const d = new Date(date.getTime() + 8 * 3600 * 1000);
        return d.toISOString().replace(/\.\d{3}Z$/, '+08:00');
      },
      sleep: () => {}
    },
    ScriptApp: {
      getProjectTriggers: () => triggers.slice(),
      deleteTrigger: (t) => {
        const idx = triggers.indexOf(t);
        if (idx >= 0) triggers.splice(idx, 1);
      },
      newTrigger: (handlerName) => ({
        timeBased: () => ({
          everyMinutes: (mins) => ({
            create: () => {
              const t = { getHandlerFunction: () => handlerName, interval: mins };
              triggers.push(t);
              return t;
            }
          })
        })
      })
    },
    DriveApp: {
      getRootFolder: () => rootFolder,
      createFolder: (name) => makeFolder('fld_' + (++nextId), name, 'root'),
      getFolderById: (id) => {
        if (!folders.has(id)) throw new Error('Folder not found: ' + id);
        return folders.get(id);
      },
      getFileById: (id) => {
        if (!files.has(id)) throw new Error('File not found: ' + id);
        return files.get(id);
      }
    },
    DocumentApp: {
      create: (name) => {
        const f = makeFile('doc_' + (++nextId), name, 'application/vnd.google-apps.document', '', 'root');
        return {
          getId: () => f.id,
          getBody: () => ({
            getText: () => f.content,
            setText: (txt) => {
              f.content = txt;
              f.updatedMs += 1000;
            }
          }),
          saveAndClose: () => {}
        };
      },
      openById: (id) => {
        docAppOpens.push(id);
        const f = files.get(id);
        if (!f) throw new Error('Doc not found: ' + id);
        return {
          getId: () => f.id,
          getBody: () => ({
            getText: () => f.content,
            setText: (txt) => {
              docAppSetTexts.push({ id, length: txt.length });
              f.content = txt;
              f.updatedMs += 1000;
            }
          }),
          saveAndClose: () => {}
        };
      }
    },
    GmailApp: {
      getDrafts: () => drafts.filter((d) => !d.deleted),
      search: (query) =>
        threads.filter((t) => {
          if (t.labels.has('Postgrad-Processed') || t.labels.has('Postgrad-Rejected')) return false;
          return t.messages.some(
            (m) =>
              m.getSubject().includes('[POSTGRAD-INBOX]') ||
              m.getSubject().includes('[POSTGRAD-REVIEW]')
          );
        }),
      getUserLabelByName: (name) => labels.get(name) || null,
      createLabel: (name) => {
        const l = { name };
        labels.set(name, l);
        return l;
      }
    },
    UrlFetchApp: {
      fetch: (url, fetchOpts) => {
        const req = {
          url,
          method: (fetchOpts.method || 'get').toLowerCase(),
          headers: fetchOpts.headers || {},
          payload: fetchOpts.payload ? JSON.parse(fetchOpts.payload) : null
        };
        ghCalls.push(req);
        const out = ghHandler(req);
        const bodyText = typeof out.body === 'string' ? out.body : JSON.stringify(out.body || {});
        return {
          getResponseCode: () => out.code,
          getContentText: () => bodyText
        };
      }
    }
  };

  if (opts.disableDriveV3 !== true) {
    sandbox.Drive = {
      Files: {
        update: (resource, fileId, blob) => {
          const f = files.get(fileId);
          if (!f) throw new Error('Drive.Files.update file not found: ' + fileId);
          const text = blob.getDataAsString();
          driveV3Updates.push({ fileId, mimeType: resource.mimeType, length: text.length });
          f.content = text;
          f.updatedMs += 1000;
          return { id: fileId };
        }
      }
    };
  }

  vm.createContext(sandbox);
  vm.runInContext(CODE_SOURCE, sandbox, { filename: 'Code.gs' });

  return {
    api: sandbox.module.exports,
    props,
    lockState,
    folders,
    files,
    makeFile,
    makeFolder,
    driveV3Updates,
    docAppOpens,
    docAppSetTexts,
    triggers,
    logs,
    drafts,
    threads,
    addDraft,
    addThread,
    ghCalls
  };
}

function makeValidStudyEnvelope(overrides = {}) {
  const reqId = overrides.request_id || 'mobile-20261121-math-taylor-001';
  return {
    target: overrides.target || `inbox/${reqId}.json`,
    request_id: reqId,
    payload: {
      schema_version: '1.0',
      request_id: overrides.payload_request_id || reqId,
      created_at: '2026-11-21T18:30:00+08:00',
      operation: 'save_study_record',
      client: 'mobile',
      payload: {
        summary: '独立完成泰勒展开，用户原话：“先看余项阶数”，并说‘这里符号要注意’。',
        subject_label: 'math',
        topic: '泰勒展开与拉格朗日余项',
        occurred_on: '2026-11-21'
      },
      ...(overrides.payloadOverrides || {})
    }
  };
}

function makeValidReviewEnvelope(overrides = {}) {
  const date = overrides.review_date || '2026-11-21';
  const reportPath = `analysis/daily/${date}.md`;
  return {
    target: reportPath,
    request_id: `review-${date}`,
    payload: {
      review_date: date,
      daily_report_path: reportPath,
      daily_report_markdown:
        `# ${date} 学习复盘\n\n本次阅读了 records/study_records.jsonl 新增记录 [R29] 并对照既有画像与事件账本进行自然语言分析，确认了中值定理构造思路的迁移进展，同时保留未验证的长期保持不确定性。\n`,
      learner_context_path: 'analysis/learner_context.md',
      learner_context_markdown:
        '---\n' +
        'analysis_type: "llm_qualitative_review"\n' +
        'reviewer: "gemini-scheduled-google-bridge"\n' +
        `reviewed_at: "${date}T02:05:00+08:00"\n` +
        `review_report: "${reportPath}"\n` +
        'study_record_count: 29\n' +
        'last_record_id: "mobile-20261121-math-taylor-001"\n' +
        'formal_event_count: 27\n' +
        'last_event_id: "mobile-20261026-mathcontest-symdiff-variant-001-attempt"\n' +
        '---\n\n' +
        '# 最新学习画像\n\n基于归档原始事实的定性工作理解，保留进展与局部待确认事项，用户当前说明优先，不替代原始记录或正式掌握度。\n',
      ...(overrides.payloadOverrides || {})
    }
  };
}

/* ============================================================================
 * 1. Manifest & Static Guardrails
 * ============================================================================ */

test('appsscript.json enables Drive v3 Advanced Service and exposes no Web App', () => {
  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
  assert.equal(manifest.runtimeVersion, 'V8');
  assert.equal(manifest.timeZone, 'Asia/Shanghai');
  const services = manifest.dependencies?.enabledAdvancedServices || [];
  assert.ok(
    services.some(
      (s) => s.userSymbol === 'Drive' && s.version === 'v3' && s.serviceId === 'drive'
    ),
    'Drive v3 Advanced Service must be declared in appsscript.json'
  );
  assert.equal(manifest.webapp, undefined, 'Must not expose public Web App');
  assert.ok(!/\bfunction\s+doPost\s*\(/.test(CODE_SOURCE), 'Code.gs must not define doPost');
  assert.ok(!/\bfunction\s+doGet\s*\(/.test(CODE_SOURCE), 'Code.gs must not define doGet');
  assert.ok(
    !/generativelanguage\.googleapis\.com|GEMINI_API_KEY/.test(CODE_SOURCE),
    'Code.gs must never call Gemini Developer API'
  );
});

/* ============================================================================
 * 2. Curly-Quote Guard & JSON Extraction
 * ============================================================================ */

test('preserves legal Chinese curly quotes inside JSON strings while rejecting structural curly quotes', () => {
  const { api } = createGasHarness();

  // Valid JSON with Chinese quotes inside strings
  const validText = JSON.stringify(makeValidStudyEnvelope(), null, 2);
  const okRes = api.parseJsonWithCurlyQuoteGuard(validText);
  assert.equal(okRes.ok, true);
  assert.ok(okRes.value.payload.payload.summary.includes('“先看余项阶数”'));
  assert.ok(okRes.value.payload.payload.summary.includes('‘这里符号要注意’'));

  // Markdown fenced JSON extraction
  const fenced = '好的，以下是提交信封：\n```json\n' + validText + '\n```\n请同步。';
  const extracted = api.extractJsonBlock(fenced);
  assert.equal(extracted.ok, true);
  assert.equal(api.parseJsonWithCurlyQuoteGuard(extracted.jsonText).ok, true);

  // Structural curly quotes outside string literals MUST be rejected with clear diagnostic
  const brokenJson = '{“target”: "inbox/mobile-20261121-test-001.json", "request_id": "mobile-20261121-test-001"}';
  const badRes = api.parseJsonWithCurlyQuoteGuard(brokenJson);
  assert.equal(badRes.ok, false);
  assert.equal(badRes.code, 'STRUCTURAL_CURLY_QUOTE');
  assert.match(badRes.error, /structural curly quote/i);
});

/* ============================================================================
 * 3. Inbox Envelope Path Whitelist, Schema Parity & Size Cap
 * ============================================================================ */

test('validateInboxEnvelope enforces strict inbox-only path whitelist and request_id alignment', () => {
  const { api } = createGasHarness();

  const good = api.validateInboxEnvelope(makeValidStudyEnvelope());
  assert.equal(good.ok, true);
  assert.equal(good.target, 'inbox/mobile-20261121-math-taylor-001.json');

  const forbiddenTargets = [
    'events/learning_events.jsonl',
    'records/study_records.jsonl',
    'outbox/mobile-20261121-math-taylor-001.json',
    'analysis/learner_context.md',
    'analysis/daily/2026-11-21.md',
    'inbox/../events/learning_events.jsonl',
    'inbox/sub/mobile-20261121-math-taylor-001.json',
    'inbox/mobile-20261121-math-taylor-001.txt',
    '/inbox/mobile-20261121-math-taylor-001.json'
  ];
  for (const target of forbiddenTargets) {
    const res = api.validateInboxEnvelope(makeValidStudyEnvelope({ target }));
    assert.equal(res.ok, false, `Expected rejection for target=${target}`);
    assert.match(res.error, /Path whitelist violation/i);
  }

  // Mismatched request_id vs target stem
  const stemMismatch = api.validateInboxEnvelope({
    ...makeValidStudyEnvelope(),
    target: 'inbox/other-id.json'
  });
  assert.equal(stemMismatch.ok, false);
  assert.match(stemMismatch.error, /does not match target filename/i);

  // Mismatched payload.request_id
  const innerMismatch = api.validateInboxEnvelope(
    makeValidStudyEnvelope({ payload_request_id: 'different-id' })
  );
  assert.equal(innerMismatch.ok, false);
  assert.match(innerMismatch.error, /payload\.request_id/);
});

test('validateInboxEnvelope enforces Core v0.5.1 study_record rules, Unicode separator guard, transcript blocker & size cap', () => {
  const { api } = createGasHarness();

  // v0.5.1 subject alias accepted
  const aliasEnv = makeValidStudyEnvelope({
    payloadOverrides: {
      payload: { summary: '独立证明完成。', subject: 'math' }
    }
  });
  assert.equal(api.validateInboxEnvelope(aliasEnv).ok, true);

  // Conflicting subject + subject_label rejected
  const conflictAlias = makeValidStudyEnvelope({
    payloadOverrides: {
      payload: { summary: '独立证明完成。', subject: 'math', subject_label: 'english' }
    }
  });
  assert.equal(api.validateInboxEnvelope(conflictAlias).ok, false);

  // Unknown extra payload field rejected
  const extraField = makeValidStudyEnvelope({
    payloadOverrides: {
      payload: { summary: '独立证明完成。', mastery: 0.9 }
    }
  });
  assert.equal(api.validateInboxEnvelope(extraField).ok, false);
  assert.match(api.validateInboxEnvelope(extraField).error, /unsupported fields: mastery/);

  // Both occurred_at and occurred_on rejected
  const bothTimes = makeValidStudyEnvelope({
    payloadOverrides: {
      payload: {
        summary: '测试',
        occurred_on: '2026-11-21',
        occurred_at: '2026-11-21T10:00:00+08:00'
      }
    }
  });
  assert.equal(api.validateInboxEnvelope(bothTimes).ok, false);

  // Invalid calendar date 2026-02-30 rejected
  const badDate = makeValidStudyEnvelope({
    payloadOverrides: {
      payload: { summary: '测试', occurred_on: '2026-02-30' }
    }
  });
  assert.equal(api.validateInboxEnvelope(badDate).ok, false);

  // Missing timezone in created_at rejected
  const naiveTs = makeValidStudyEnvelope({
    payloadOverrides: { created_at: '2026-11-21T18:30:00' }
  });
  assert.equal(api.validateInboxEnvelope(naiveTs).ok, false);

  // Unicode line separators U+2028/U+2029/U+0085 rejected to protect Core v0.5.1 JSONL reader
  const unicodeSep = makeValidStudyEnvelope({
    payloadOverrides: {
      payload: { summary: '第一行\u2028第二行' }
    }
  });
  assert.equal(api.validateInboxEnvelope(unicodeSep).ok, false);
  assert.match(api.validateInboxEnvelope(unicodeSep).error, /Unicode line separator/);

  // Full-chat transcript fields rejected
  const transcriptPayload = makeValidStudyEnvelope({
    payloadOverrides: {
      operation: 'project_change_request',
      payload: { title: 't', description: 'd', chat_transcript: 'full chat' }
    }
  });
  assert.equal(api.validateInboxEnvelope(transcriptPayload).ok, false);
  assert.match(api.validateInboxEnvelope(transcriptPayload).error, /full-chat fields/);

  // Nested non-string enum (Core v0.5.1 TypeError bug) blocked before reaching inbox
  const badUnitStatus = makeValidStudyEnvelope({
    payloadOverrides: {
      operation: 'register_unit',
      payload: {
        unit: {
          schema_version: '1.0',
          unit_id: 'math.sample.unit',
          subject: 'math',
          title: 'Test',
          status: []
        }
      }
    }
  });
  assert.equal(api.validateInboxEnvelope(badUnitStatus).ok, false);

  // Size limit enforcement
  const oversized = makeValidStudyEnvelope({
    payloadOverrides: {
      payload: { summary: '数'.repeat(5000) }
    }
  });
  const capRes = api.validateInboxEnvelope(oversized, { maxBytes: 1024 });
  assert.equal(capRes.ok, false);
  assert.match(capRes.error, /exceeds maximum allowed size/);
});

/* ============================================================================
 * 4. GitHub GET-before-PUT Idempotency, Conflict Guard & 422 Race Handling
 * ============================================================================ */

test('uploadInboxToGitHub checks GET first: creates on 404, skips on identical, rejects on conflict', () => {
  const remoteFiles = new Map();
  const h = createGasHarness({
    githubHandler: (req) => {
      const m = /\/contents\/(.+?)(\?|$)/.exec(req.url);
      if (m) {
        const repoPath = decodeURIComponent(m[1]);
        if (req.method === 'get') {
          if (!remoteFiles.has(repoPath)) return { code: 404, body: { message: 'Not Found' } };
          return { code: 200, body: { sha: 'sha1', content: b64(remoteFiles.get(repoPath)) } };
        }
        if (req.method === 'put') {
          assert.equal(req.payload.sha, undefined, 'Inbox PUT must never pass sha to overwrite');
          if (remoteFiles.has(repoPath)) return { code: 422, body: { message: 'sha wasn\'t supplied' } };
          remoteFiles.set(repoPath, unb64(req.payload.content));
          return { code: 201, body: { commit: { sha: 'commit_abc1234' } } };
        }
      }
      return { code: 404, body: {} };
    }
  });

  const cfg = { githubOwner: 'example-learner', githubRepo: 'example-study-vault', githubBranch: 'main', githubToken: 'tok' };
  const val = h.api.validateInboxEnvelope(makeValidStudyEnvelope());
  assert.equal(val.ok, true);

  // 1st upload: 404 -> PUT 201
  const first = h.api.uploadInboxToGitHub(cfg, val);
  assert.equal(first.outcome, 'uploaded');
  assert.ok(remoteFiles.has(val.target));

  // 2nd upload with semantically identical JSON (reordered keys): GET 200 -> idempotent_skip (no PUT)
  const callsBefore = h.ghCalls.length;
  const second = h.api.uploadInboxToGitHub(cfg, val);
  assert.equal(second.outcome, 'idempotent_skip');
  assert.equal(h.ghCalls.length, callsBefore + 1);
  assert.equal(h.ghCalls[h.ghCalls.length - 1].method, 'get');

  // 3rd upload with SAME request_id but DIFFERENT summary: GET 200 -> conflict (never overwrites)
  const altered = h.api.validateInboxEnvelope(
    makeValidStudyEnvelope({
      payloadOverrides: {
        payload: { summary: '被篡改的不同摘要内容', subject_label: 'math' }
      }
    })
  );
  const third = h.api.uploadInboxToGitHub(cfg, altered);
  assert.equal(third.outcome, 'conflict');
  assert.match(third.error, /Refusing to overwrite/i);
  assert.ok(remoteFiles.get(val.target).includes('独立完成泰勒展开'));
});

/* ============================================================================
 * 5. Authorized Daily Review Channel Isolation & Atomic Commit
 * ============================================================================ */

test('review envelope enforces strict path/frontmatter/non-regression guards and atomic commit', () => {
  const { api } = createGasHarness();

  // Channel isolation: review envelope submitted via [POSTGRAD-INBOX] MUST be rejected
  const revEnv = makeValidReviewEnvelope();
  const wrongChannel = api.processRawUplinkText(
    { maxInboxBytes: 65536, maxReviewReportBytes: 65536, maxReviewContextBytes: 32768 },
    JSON.stringify(revEnv),
    'inbox',
    'gmail_draft'
  );
  assert.equal(wrongChannel.outcome, 'rejected');
  assert.match(wrongChannel.error, /Path whitelist violation/i);

  // Valid review envelope passes local validation
  const okRev = api.validateReviewEnvelope(revEnv);
  assert.equal(okRev.ok, true);
  assert.equal(okRev.frontmatter.study_record_count, 29);

  // Missing analysis_type llm_qualitative_review rejected
  const badType = makeValidReviewEnvelope();
  badType.payload.learner_context_markdown = badType.payload.learner_context_markdown.replace(
    'llm_qualitative_review',
    'gpt_qualitative_review'
  );
  assert.equal(api.validateReviewEnvelope(badType).ok, false);

  // Unauthorized learner_context_path rejected
  const badCtxPath = makeValidReviewEnvelope({
    payloadOverrides: { learner_context_path: 'learner_profile.md' }
  });
  assert.equal(api.validateReviewEnvelope(badCtxPath).ok, false);

  // Atomic publish + regression guard
  let patchedTree = null;
  let patchedForce = null;
  const h = createGasHarness({
    githubHandler: (req) => {
      if (req.url.includes('/contents/analysis/daily/2026-11-21.md')) return { code: 404, body: {} };
      if (req.url.includes('/contents/analysis/learner_context.md')) {
        return {
          code: 200,
          body: {
            sha: 'old_ctx',
            content: b64(
              '---\nanalysis_type: "gpt_qualitative_review"\nstudy_record_count: 28\nformal_event_count: 27\n---\nold\n'
            )
          }
        };
      }
      if (req.method === 'get' && req.url.endsWith('/git/ref/heads/main')) {
        return { code: 200, body: { object: { sha: 'head_1' } } };
      }
      if (req.method === 'get' && req.url.endsWith('/git/commits/head_1')) {
        return { code: 200, body: { tree: { sha: 'tree_1' } } };
      }
      if (req.method === 'post' && req.url.endsWith('/git/blobs')) {
        return { code: 201, body: { sha: 'blob_' + h.ghCalls.length } };
      }
      if (req.method === 'post' && req.url.endsWith('/git/trees')) {
        patchedTree = req.payload.tree;
        return { code: 201, body: { sha: 'tree_2' } };
      }
      if (req.method === 'post' && req.url.endsWith('/git/commits')) {
        return { code: 201, body: { sha: 'commit_2' } };
      }
      if (req.method === 'patch' && req.url.endsWith('/git/refs/heads/main')) {
        patchedForce = req.payload.force;
        return { code: 200, body: { object: { sha: 'commit_2' } } };
      }
      return { code: 404, body: {} };
    }
  });

  const cfg = {
    githubOwner: 'example-learner',
    githubRepo: 'example-study-vault',
    githubBranch: 'main',
    githubToken: 'tok',
    allowDailyReviewPublish: true
  };
  const pubRes = h.api.publishDailyReviewToGitHub(cfg, h.api.validateReviewEnvelope(revEnv));
  assert.equal(pubRes.outcome, 'uploaded');
  assert.equal(patchedForce, false, 'Must use non-force ref update');
  assert.deepEqual(
    patchedTree.map((x) => x.path),
    ['analysis/daily/2026-11-21.md', 'analysis/learner_context.md']
  );

  // Regression guard: study_record_count=20 < existing 28 -> rejected
  const regressedEnv = makeValidReviewEnvelope();
  regressedEnv.payload.learner_context_markdown = regressedEnv.payload.learner_context_markdown.replace(
    'study_record_count: 29',
    'study_record_count: 20'
  );
  const regRes = h.api.publishDailyReviewToGitHub(cfg, h.api.validateReviewEnvelope(regressedEnv));
  assert.equal(regRes.outcome, 'rejected');
  assert.match(regRes.error, /Regression guard/i);
});

/* ============================================================================
 * 6. End-to-End runBridgeCycle: Lock, 4 Uplink Channels, Outbox Poll & Downlink
 * ============================================================================ */

test('runBridgeCycle respects ScriptLock when busy', () => {
  const h = createGasHarness({ lockBusy: true });
  const res = h.api.runBridgeCycle();
  assert.equal(res.status, 'skipped_lock_busy');
  assert.equal(h.ghCalls.length, 0);
});

test('runBridgeCycle handles Gmail drafts, sent mail, Drive inbox, Queue fast-path, outbox polling & Drive v3 downlink', () => {
  const repoFiles = new Map([
    ['engine.lock.json', '{"version":"v0.5.1","commit":"8b90d71f5051742980a9702a46569b4c2416e3d4"}'],
    ['MOBILE_STUDY.md', '# Mobile Study\n'],
    ['analysis/learner_context.md', '---\nstudy_record_count: 1\n---\n# 画像\n'],
    ['analysis/daily/2026-11-04.md', '# 2026-11-04 复盘\n'],
    ['exports/latest.md', '# Capsule\n'],
    ['exports/study_records.json', '{"stored_count":1}'],
    ['state/knowledge_units.json', '{"units":[]}'],
    ['records/study_records.jsonl', '{"record_id":"r-001","summary":"测试记录"}\n'],
    ['events/learning_events.jsonl', '{"event_id":"e-001"}\n']
  ]);

  let currentHead = 'head_aaa1111';
  const h = createGasHarness({
    githubHandler: (req) => {
      if (req.method === 'get' && req.url.endsWith('/git/ref/heads/main')) {
        return { code: 200, body: { object: { sha: currentHead } } };
      }
      if (req.method === 'get' && req.url.includes('/git/trees/')) {
        const tree = [...repoFiles.keys()].map((p, idx) => ({
          path: p,
          type: 'blob',
          sha: 'blob_' + p.replace(/[^a-z0-9]/gi, '_') + '_' + repoFiles.get(p).length + '_' + idx
        }));
        return { code: 200, body: { tree } };
      }
      if (req.method === 'get' && req.url.includes('/git/blobs/')) {
        const blobSha = req.url.split('/git/blobs/')[1];
        for (const [p, content] of repoFiles.entries()) {
          if (blobSha.startsWith('blob_' + p.replace(/[^a-z0-9]/gi, '_') + '_')) {
            return { code: 200, body: { content: b64(content), encoding: 'base64' } };
          }
        }
        return { code: 404, body: {} };
      }
      const m = /\/contents\/(.+?)(\?|$)/.exec(req.url);
      if (m) {
        const repoPath = decodeURIComponent(m[1]);
        if (req.method === 'get') {
          if (!repoFiles.has(repoPath)) return { code: 404, body: { message: 'Not Found' } };
          return { code: 200, body: { sha: 'file_sha', content: b64(repoFiles.get(repoPath)) } };
        }
        if (req.method === 'put') {
          const decoded = unb64(req.payload.content);
          repoFiles.set(repoPath, decoded);
          // Simulate GitHub Actions immediately producing matching outbox receipt
          const parsed = JSON.parse(decoded);
          repoFiles.set(
            `outbox/${parsed.request_id}.json`,
            JSON.stringify({
              schema_version: '1.0',
              request_id: parsed.request_id,
              operation: parsed.operation,
              status: 'succeeded',
              processed_at: '2026-11-21T18:31:00Z',
              result: { record_id: parsed.request_id, record_status: 'stored' }
            })
          );
          currentHead = 'head_bbb2222';
          return { code: 201, body: { commit: { sha: currentHead } } };
        }
      }
      return { code: 404, body: {} };
    }
  });

  // 1. Setup bridge (creates folders, docs, trigger, initial downlink)
  const setupRes = h.api.setupBridge();
  assert.equal(setupRes.status, 'ok');
  assert.equal(h.triggers.length, 1);
  assert.equal(h.triggers[0].interval, 5);
  assert.equal(h.driveV3Updates.length >= 4, true, 'Downlink + SyncLog must use Drive v3 update');
  assert.equal(h.docAppSetTexts.length, 0, 'Must NOT fall back to DocumentApp.setText when Drive v3 is available');

  // Verify Postgrad-3 has indexed ledger lines
  const ledgerDoc = h.files.get(setupRes.resources.ledgersDocId);
  assert.ok(ledgerDoc.content.includes('study_record_count: 1'));
  assert.ok(ledgerDoc.content.includes('[R01] {"record_id":"r-001","summary":"测试记录"}'));
  assert.ok(ledgerDoc.content.includes('[E01] {"event_id":"e-001"}'));

  // 2. Add a valid Gmail draft, an invalid curly-quote Gmail draft, a sent email, and a Drive inbox file
  const goodDraft = h.addDraft({
    subject: '[POSTGRAD-INBOX] mobile-20261121-draft-001',
    body: JSON.stringify(makeValidStudyEnvelope({ request_id: 'mobile-20261121-draft-001' }))
  });
  const badDraft = h.addDraft({
    subject: '[POSTGRAD-INBOX] mobile-20261121-bad-001',
    body: '{“target”: "inbox/mobile-20261121-bad-001.json", "request_id": "mobile-20261121-bad-001"}'
  });
  const sentThread = h.addThread({
    subject: '[POSTGRAD-INBOX] mobile-20261121-sent-001',
    body: JSON.stringify(makeValidStudyEnvelope({ request_id: 'mobile-20261121-sent-001' }))
  });
  const driveInboxFile = h.makeFile(
    'inbox_file_1',
    'note.json',
    'application/json',
    JSON.stringify(makeValidStudyEnvelope({ request_id: 'mobile-20261121-drive-001' })),
    setupRes.resources.inboxFolderId
  );

  // Set queue doc watermark to current updatedMs to verify fast-path DOES NOT open it
  const queueFile = h.files.get(setupRes.resources.queueDocId);
  h.props.QUEUE_DOC_LAST_UPDATED_MS = String(queueFile.updatedMs);
  h.docAppOpens.length = 0;

  // 3. Run bridge cycle
  const cycle1 = h.api.runBridgeCycle();
  assert.equal(cycle1.uplink.uploaded, 3);
  assert.equal(cycle1.uplink.rejected, 1);
  assert.equal(cycle1.outbox_resolved.length, 3);
  assert.equal(goodDraft.deleted, true, 'Succeeded draft must be deleted immediately');
  assert.equal(badDraft.deleted, false);
  assert.ok(badDraft.subject.startsWith('[POSTGRAD-REJECTED]'));
  assert.ok(badDraft.body.includes('POSTGRAD BRIDGE REJECTED'));
  assert.ok(badDraft.body.includes('structural curly quote'));
  assert.equal(sentThread.labels.has('Postgrad-Processed'), true);
  assert.equal(driveInboxFile.parentId, setupRes.resources.processedFolderId);
  assert.equal(
    h.docAppOpens.includes(setupRes.resources.queueDocId),
    false,
    'Unchanged Queue Doc must NOT be opened'
  );

  // Verify Sync Log Doc recorded the resolved receipts
  const syncLogDoc = h.files.get(setupRes.resources.syncLogDocId);
  assert.ok(syncLogDoc.content.includes('[succeeded] mobile-20261121-draft-001'));

  // 4. Next cycle with NO changes: HEAD unchanged -> downlink skipped, 0 Drive updates!
  const v3BeforeIdle = h.driveV3Updates.length;
  const ghBeforeIdle = h.ghCalls.length;
  const cycle2 = h.api.runBridgeCycle();
  assert.equal(cycle2.downlink.skipped, true);
  assert.equal(cycle2.downlink.reason, 'head_unchanged');
  assert.equal(h.driveV3Updates.length, v3BeforeIdle, 'No Drive writes on idle cycle');
  assert.equal(h.ghCalls.length - ghBeforeIdle, 1, 'Idle cycle should make only 1 GitHub HEAD check');
  assert.equal(h.lockState.acquiredCount, h.lockState.releasedCount, 'ScriptLock must always be released');
});

test('writeDocPreservingId falls back to DocumentApp only when Drive v3 is unavailable', () => {
  const h = createGasHarness({ disableDriveV3: true });
  const f = h.makeFile('doc_fallback', 'TestDoc', 'application/vnd.google-apps.document', 'old', 'root');
  const res = h.api.writeDocPreservingId(f.id, 'new content');
  assert.equal(res.method, 'document_app_fallback');
  assert.equal(f.content, 'new content');
  assert.equal(h.docAppSetTexts.length, 1);
});

test('Drive Queue Doc processes modified multi-item queue, clears succeeded, annotates rejected, and updates watermark', () => {
  const repoFiles = new Map([
    ['engine.lock.json', '{"version":"v0.5.1"}']
  ]);
  const h = createGasHarness({
    githubHandler: (req) => {
      if (req.method === 'get' && req.url.endsWith('/git/ref/heads/main')) {
        return { code: 200, body: { object: { sha: 'head_q1' } } };
      }
      if (req.method === 'get' && req.url.includes('/git/trees/')) {
        return { code: 200, body: { tree: [{ path: 'engine.lock.json', type: 'blob', sha: 'b1' }] } };
      }
      if (req.method === 'get' && req.url.includes('/git/blobs/')) {
        return { code: 200, body: { content: b64('{"version":"v0.5.1"}'), encoding: 'base64' } };
      }
      const m = /\/contents\/(.+?)(\?|$)/.exec(req.url);
      if (m) {
        const repoPath = decodeURIComponent(m[1]);
        if (req.method === 'get') {
          if (!repoFiles.has(repoPath)) return { code: 404, body: {} };
          return { code: 200, body: { sha: 's', content: b64(repoFiles.get(repoPath)) } };
        }
        if (req.method === 'put') {
          repoFiles.set(repoPath, unb64(req.payload.content));
          return { code: 201, body: { commit: { sha: 'head_q2' } } };
        }
      }
      return { code: 404, body: {} };
    }
  });

  const setup = h.api.setupBridge();
  const queueFile = h.files.get(setup.resources.queueDocId);
  const validItem = JSON.stringify(makeValidStudyEnvelope({ request_id: 'mobile-20261121-queue-001' }));
  const badItem = JSON.stringify({ target: 'events/learning_events.jsonl', request_id: 'bad', payload: {} });
  queueFile.content = h.api.QUEUE_DOC_HEADER + '\n' + validItem + '\n===POSTGRAD-ITEM===\n' + badItem + '\n';
  queueFile.updatedMs += 5000;

  const res = h.api.runBridgeCycle();
  assert.equal(res.uplink.uploaded, 1);
  assert.equal(res.uplink.rejected, 1);
  assert.ok(repoFiles.has('inbox/mobile-20261121-queue-001.json'));
  assert.ok(!queueFile.content.includes('mobile-20261121-queue-001'), 'Succeeded queue item should be removed');
  assert.ok(queueFile.content.includes('[POSTGRAD-REJECTED]'), 'Rejected queue item should remain annotated');

  // Outbox was not yet ready in cycle 1 -> must be tracked in PENDING_OUTBOX_IDS
  assert.deepEqual(JSON.parse(h.props.PENDING_OUTBOX_IDS), ['mobile-20261121-queue-001']);

  // Simulate GitHub Actions finishing before cycle 2
  repoFiles.set(
    'outbox/mobile-20261121-queue-001.json',
    JSON.stringify({
      schema_version: '1.0',
      request_id: 'mobile-20261121-queue-001',
      operation: 'save_study_record',
      status: 'succeeded',
      processed_at: '2026-11-21T19:00:00Z',
      result: { record_id: 'mobile-20261121-queue-001' }
    })
  );

  // Cycle 2 resolves pending receipt without re-opening unchanged queue doc
  h.docAppOpens.length = 0;
  const res2 = h.api.runBridgeCycle();
  assert.equal(res2.outbox_resolved.length, 1);
  assert.equal(res2.outbox_resolved[0].status, 'succeeded');
  assert.deepEqual(JSON.parse(h.props.PENDING_OUTBOX_IDS), []);
  assert.equal(h.docAppOpens.includes(setup.resources.queueDocId), false);
});

test('uploadInboxToGitHub resolves 422 concurrent creation race via re-GET', () => {
  const env = makeValidStudyEnvelope({ request_id: 'mobile-20261121-race-001' });
  const serialized = JSON.stringify(env.payload, null, 2) + '\n';
  let getCalls = 0;
  const h = createGasHarness({
    githubHandler: (req) => {
      if (req.method === 'get') {
        getCalls += 1;
        if (getCalls === 1) return { code: 404, body: {} };
        return { code: 200, body: { sha: 's', content: b64(serialized) } };
      }
      if (req.method === 'put') {
        return { code: 422, body: { message: 'sha wasn\'t supplied' } };
      }
      return { code: 404, body: {} };
    }
  });

  const cfg = { githubOwner: 'example-learner', githubRepo: 'example-study-vault', githubBranch: 'main', githubToken: 'tok' };
  const val = h.api.validateInboxEnvelope(env);
  const res = h.api.uploadInboxToGitHub(cfg, val);
  assert.equal(res.outcome, 'idempotent_skip');
  assert.equal(getCalls, 2);
});

