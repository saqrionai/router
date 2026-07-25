export const meta = {
  name: 'fugu-forum',
  description: 'Fugu-routed native queue with independent evidence, implementation, verification, judgment, and bounded revision',
  phases: [
    { title: 'Opening posts', detail: 'independent evidence and hypotheses' },
    { title: 'Cross-examination', detail: 'scope-bounded falsification' },
    { title: 'Artifact workshop', detail: 'routed implementation or experiment' },
    { title: 'Verification', detail: 'independent artifact and machine checks' },
    { title: 'Judgment', detail: 'criterion-level evidence gate' },
    { title: 'Revision', detail: 'bounded evaluator-optimizer queue' },
  ],
}

let input = {}
if (args && typeof args === 'object') {
  input = args
} else if (typeof args === 'string' && args.trim()) {
  try {
    input = JSON.parse(args)
  } catch {
    return { status: 'rejected', reason: 'fugu-forum args must be valid JSON' }
  }
}
const task = String(input.task || '').trim()
if (!task) {
  return { status: 'rejected', reason: 'fugu-forum requires args.task' }
}

const workspace = String(input.workspace || '.')
const authorization = String(
  input.authorization || 'No security authorization was supplied.',
)
const acceptance = Array.isArray(input.acceptanceCriteria)
  ? input.acceptanceCriteria.map(String).map(item => item.trim()).filter(Boolean)
  : []
const assignments = Array.isArray(input.assignments) ? input.assignments : []
const tracking = input.tracking && typeof input.tracking === 'object'
  ? input.tracking
  : null
const ultracheck = Boolean(input.ultracheck) || /\bultracheck\b/i.test(task)
const fullForum = ultracheck
  || Boolean(input.fullForum)
  || /\bfull forum\b/i.test(task)
const quick = !fullForum && Boolean(input.quick)
const mode = quick ? 'quick' : fullForum ? 'full' : 'standard'
const workflowRunId = String(input.workflowRunId || '').trim()
if (!workflowRunId) {
  return {
    status: 'rejected',
    reason: 'fugu-forum requires args.workflowRunId from Fugu route_team',
  }
}
const defaultMaxRounds = quick ? 1 : fullForum ? 3 : 2
const maxRoundCeiling = defaultMaxRounds
const maxRounds = Math.max(
  1,
  Math.min(Number(input.maxRounds || defaultMaxRounds), maxRoundCeiling),
)
const noProgressLimit = Math.max(
  1,
  Math.min(Number(input.noProgressLimit || 2), 3),
)
const routeByPersona = Object.fromEntries(
  assignments.map(item => [String(item.persona), item]),
)

const workerSchema = {
  type: 'object',
  required: [
    'status',
    'summary',
    'claims',
    'evidence',
    'checks',
    'unresolved',
    'nextActions',
  ],
  properties: {
    status: {
      type: 'string',
      enum: ['completed', 'blocked', 'failed'],
    },
    summary: { type: 'string' },
    claims: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'status', 'evidenceIds'],
        properties: {
          claim: { type: 'string' },
          status: {
            type: 'string',
            enum: ['supported', 'refuted', 'hypothesis', 'unverified'],
          },
          evidenceIds: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    evidence: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'source', 'observation'],
        properties: {
          id: { type: 'string' },
          source: { type: 'string' },
          observation: { type: 'string' },
        },
      },
    },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'status', 'evidence'],
        properties: {
          name: { type: 'string' },
          command: { type: 'string' },
          status: {
            type: 'string',
            enum: ['passed', 'failed', 'errored', 'not-run', 'not-applicable'],
          },
          evidence: { type: 'string' },
        },
      },
    },
    unresolved: { type: 'array', items: { type: 'string' } },
    nextActions: { type: 'array', items: { type: 'string' } },
  },
}

const ultraSchema = {
  type: 'object',
  required: [
    'status',
    'summary',
    'broadChecks',
    'cleanRerun',
    'hypotheses',
    'hostileInputs',
    'evidenceLedger',
    'unresolved',
    'nextActions',
  ],
  properties: {
    status: {
      type: 'string',
      enum: ['completed', 'blocked', 'failed'],
    },
    summary: { type: 'string' },
    broadChecks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['category', 'applicable', 'status', 'evidence'],
        properties: {
          category: {
            type: 'string',
            enum: ['acceptance', 'tests', 'build', 'typecheck', 'lint'],
          },
          applicable: { type: 'boolean' },
          status: {
            type: 'string',
            enum: ['passed', 'failed', 'errored', 'not-run', 'not-applicable'],
          },
          evidence: { type: 'string' },
        },
      },
    },
    cleanRerun: {
      type: 'object',
      required: ['performed', 'status', 'evidence'],
      properties: {
        performed: { type: 'boolean' },
        status: {
          type: 'string',
          enum: ['passed', 'failed', 'errored', 'not-run'],
        },
        evidence: { type: 'string' },
      },
    },
    hypotheses: {
      type: 'array',
      minItems: 5,
      items: {
        type: 'object',
        required: ['hypothesis', 'test', 'status', 'evidence'],
        properties: {
          hypothesis: { type: 'string' },
          test: { type: 'string' },
          status: {
            type: 'string',
            enum: ['refuted', 'survived', 'unresolved'],
          },
          evidence: { type: 'string' },
        },
      },
    },
    hostileInputs: {
      type: 'array',
      items: {
        type: 'object',
        required: ['category', 'applicable', 'status', 'evidence'],
        properties: {
          category: {
            type: 'string',
            enum: [
              'empty',
              'null',
              'zero',
              'negative',
              'huge',
              'malformed',
              'unicode',
              'duplicate',
              'error-path',
              'boundary',
            ],
          },
          applicable: { type: 'boolean' },
          status: {
            type: 'string',
            enum: ['passed', 'failed', 'not-run', 'not-applicable'],
          },
          evidence: { type: 'string' },
        },
      },
    },
    evidenceLedger: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'status', 'evidence'],
        properties: {
          claim: { type: 'string' },
          status: {
            type: 'string',
            enum: ['supported', 'refuted', 'unverified'],
          },
          evidence: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    unresolved: { type: 'array', items: { type: 'string' } },
    nextActions: { type: 'array', items: { type: 'string' } },
  },
}

const judgeSchema = {
  type: 'object',
  required: [
    'decision',
    'summary',
    'criteria',
    'completionClaims',
    'blockers',
    'nextActions',
    'progress',
  ],
  properties: {
    decision: {
      type: 'string',
      enum: ['accept', 'revise', 'reject', 'inconclusive'],
    },
    summary: { type: 'string' },
    criteria: {
      type: 'array',
      items: {
        type: 'object',
        required: ['criterion', 'status', 'evidence'],
        properties: {
          criterion: { type: 'string' },
          status: {
            type: 'string',
            enum: ['passed', 'failed', 'unverified'],
          },
          evidence: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    completionClaims: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'status', 'evidence'],
        properties: {
          claim: { type: 'string' },
          status: {
            type: 'string',
            enum: ['supported', 'refuted', 'unverified'],
          },
          evidence: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    blockers: { type: 'array', items: { type: 'string' } },
    nextActions: { type: 'array', items: { type: 'string' } },
    progress: {
      type: 'object',
      required: ['artifactChanged', 'newEvidence', 'newChecks'],
      properties: {
        artifactChanged: { type: 'boolean' },
        newEvidence: { type: 'boolean' },
        newChecks: { type: 'boolean' },
      },
    },
  },
}

const personaPrompts = {
  researcher: 'Inventory primary evidence, prior work, relevant files, and missing artifacts. State exactly what each source supports and does not support.',
  bullshitter: 'Generate high-upside competing hypotheses. Mark every novel assertion as a hypothesis and give a concrete falsification test. Never manufacture evidence.',
  exploiter: 'For the authorized target only, analyze reachable trust boundaries, primitives, preconditions, constraints, and failure points. Distinguish plausible from demonstrated.',
  engineer: 'Implement the smallest sound artifact or experiment that advances the task. Follow repository conventions and run real acceptance checks before claiming success.',
  verifier: 'Try to falsify the important claims using direct artifact inspection and reproducible machine checks. Explain what every check proves and does not prove.',
  judge: 'Resolve every exact acceptance criterion. A returned worker result is testimony, not proof. Reject unsupported certainty and checks that were not actually run.',
}

const queue = []
let nextQueueId = 1

function enqueue(persona, phaseName, objective, round) {
  const item = {
    id: `unit-${nextQueueId++}`,
    persona,
    phase: phaseName,
    objective,
    round,
    status: 'queued',
    model: null,
    attemptedModels: [],
    routeAttempts: [],
    degradationReasons: [],
  }
  queue.push(item)
  return item
}

function updateQueue(item, status, values = {}) {
  Object.assign(item, values, { status })
  log(`${item.id} ${item.persona}: ${status}${item.model ? ` via ${item.model}` : ''}`)
}

function queueSnapshot() {
  return queue.map(item => ({
    id: item.id,
    persona: item.persona,
    phase: item.phase,
    round: item.round,
    status: item.status,
    model: item.model,
    attemptedModels: item.attemptedModels,
    routeAttempts: item.routeAttempts,
    degradationReasons: item.degradationReasons,
    workerStatus: item.workerStatus || null,
    summary: item.summary || null,
    reason: item.reason || null,
  }))
}

function agentTypeForModel(model) {
  if (model.startsWith('fable-5')) return 'orchestrator:fable-neutral'
  if (model.startsWith('gpt-5.6')) return 'orchestrator:codex-worker'
  if (model.startsWith('opus-4.8')) return 'orchestrator:opus-48-recovery'
  return 'orchestrator:opus-worker'
}

function routes(persona) {
  const selected = routeByPersona[persona] || {}
  const primary = String(selected.model || 'opus-5-bounded')
  const models = [
    primary,
    ...(Array.isArray(selected.fallback_order)
      ? selected.fallback_order.map(String)
      : []),
  ]
  return Array.from(new Set(models)).slice(0, 4).map((model, index) => ({
    model,
    agentType: index === 0 && selected.agent_type
      ? String(selected.agent_type)
      : agentTypeForModel(model),
  }))
}

function excerpt(value, limit = 14000) {
  const rendered = typeof value === 'string' ? value : JSON.stringify(value)
  return rendered.length <= limit
    ? rendered
    : `${rendered.slice(0, limit)}\n[truncated by workflow]`
}

function validWorkerResult(result) {
  return Boolean(
    result
      && typeof result === 'object'
      && ['completed', 'blocked'].includes(result.status)
      && typeof result.summary === 'string'
      && Array.isArray(result.claims)
      && Array.isArray(result.evidence)
      && Array.isArray(result.checks)
      && Array.isArray(result.unresolved)
      && Array.isArray(result.nextActions),
  )
}

function validUltraResult(result) {
  return Boolean(
    result
      && typeof result === 'object'
      && ['completed', 'blocked'].includes(result.status)
      && typeof result.summary === 'string'
      && Array.isArray(result.broadChecks)
      && result.cleanRerun
      && typeof result.cleanRerun === 'object'
      && Array.isArray(result.hypotheses)
      && Array.isArray(result.hostileInputs)
      && Array.isArray(result.evidenceLedger)
      && Array.isArray(result.unresolved)
      && Array.isArray(result.nextActions),
  )
}

function validJudgeResult(result) {
  return Boolean(
    result
      && typeof result === 'object'
      && ['accept', 'revise', 'reject', 'inconclusive'].includes(result.decision)
      && typeof result.summary === 'string'
      && Array.isArray(result.criteria)
      && Array.isArray(result.completionClaims)
      && Array.isArray(result.blockers)
      && Array.isArray(result.nextActions)
      && result.progress
      && typeof result.progress === 'object',
  )
}

function workerDegradationReasons(result, persona) {
  const reasons = []
  const summary = String(result.summary || '').trim()
  const claims = Array.isArray(result.claims) ? result.claims : []
  const evidence = Array.isArray(result.evidence) ? result.evidence : []
  const checks = Array.isArray(result.checks) ? result.checks : []
  const unresolved = Array.isArray(result.unresolved) ? result.unresolved : []
  const nextActions = Array.isArray(result.nextActions) ? result.nextActions : []

  if (!summary) reasons.push('empty summary')
  if (
    result.status === 'completed'
    && claims.length === 0
    && evidence.length === 0
    && checks.length === 0
  ) {
    reasons.push('completed result contains no claims, evidence, or checks')
  }
  if (
    result.status === 'blocked'
    && unresolved.length === 0
    && nextActions.length === 0
  ) {
    reasons.push('blocked result gives no unresolved issue or next action')
  }
  if (
    result.status === 'completed'
    && persona === 'researcher'
    && evidence.length === 0
  ) {
    reasons.push('researcher completed without an evidence inventory')
  }
  if (
    result.status === 'completed'
    && ['bullshitter', 'exploiter'].includes(persona)
    && claims.length === 0
  ) {
    reasons.push(`${persona} completed without claims or hypotheses`)
  }
  if (
    result.status === 'completed'
    && persona === 'engineer'
    && claims.length === 0
    && checks.length === 0
  ) {
    reasons.push('engineer completed without an artifact claim or check')
  }
  if (
    result.status === 'completed'
    && persona === 'verifier'
    && evidence.length === 0
    && checks.length === 0
  ) {
    reasons.push('verifier completed without evidence or machine checks')
  }

  const evidenceIds = evidence.map(item => String(item.id || '').trim())
  if (evidenceIds.some(id => !id)) {
    reasons.push('evidence contains an empty identifier')
  }
  if (new Set(evidenceIds).size !== evidenceIds.length) {
    reasons.push('evidence identifiers are not unique')
  }
  if (evidence.some(item => (
    !String(item.source || '').trim()
    || !String(item.observation || '').trim()
  ))) {
    reasons.push('evidence contains an empty source or observation')
  }
  if (claims.some(item => (
    item.status === 'supported'
    && (
      !Array.isArray(item.evidenceIds)
      || item.evidenceIds.length === 0
      || item.evidenceIds.some(id => (
        !String(id || '').trim()
        || !evidenceIds.includes(String(id).trim())
      ))
    )
  ))) {
    reasons.push('a supported claim has blank or dangling evidence identifiers')
  }
  if (checks.some(item => (
    item.status === 'passed' && !String(item.evidence || '').trim()
  ))) {
    reasons.push('a passed check has no observed evidence')
  }

  return Array.from(new Set(reasons))
}

function judgeDegradationReasons(result) {
  const reasons = []
  const criteria = Array.isArray(result.criteria) ? result.criteria : []
  const completionClaims = Array.isArray(result.completionClaims)
    ? result.completionClaims
    : []
  const blockers = Array.isArray(result.blockers) ? result.blockers : []
  const nextActions = Array.isArray(result.nextActions) ? result.nextActions : []

  if (!String(result.summary || '').trim()) reasons.push('empty judge summary')
  if (
    acceptance.length
    && (
      criteria.length !== acceptance.length
      || criteria.some((row, index) => (
        String(row.criterion || '').trim() !== acceptance[index]
      ))
    )
  ) {
    reasons.push('judge did not return every exact acceptance criterion')
  }
  if (criteria.some(row => (
    row.status === 'passed'
    && (
      !Array.isArray(row.evidence)
      || row.evidence.length === 0
      || row.evidence.some(item => !String(item || '').trim())
    )
  ))) {
    reasons.push('a passed criterion has blank or missing evidence')
  }
  if (completionClaims.some(row => (
    row.status === 'supported'
    && (
      !Array.isArray(row.evidence)
      || row.evidence.length === 0
      || row.evidence.some(item => !String(item || '').trim())
    )
  ))) {
    reasons.push('a supported completion claim has blank or missing evidence')
  }
  if (
    result.decision === 'accept'
    && (
      blockers.length > 0
      || criteria.some(row => row.status !== 'passed')
    )
  ) {
    reasons.push('accept decision contradicts blockers or criterion status')
  }
  if (
    result.decision === 'revise'
    && blockers.length === 0
    && nextActions.length === 0
  ) {
    reasons.push('revise decision gives no blocker or next action')
  }
  return Array.from(new Set(reasons))
}

function ultraDegradationReasons(result) {
  const reasons = []
  if (!String(result.summary || '').trim()) {
    reasons.push('empty UltraCheck summary')
  }
  if (
    result.status === 'blocked'
    && result.unresolved.length === 0
    && result.nextActions.length === 0
  ) {
    reasons.push('blocked UltraCheck gives no unresolved issue or next action')
  }
  if (result.status === 'completed') {
    const broadCategories = new Set(
      result.broadChecks.map(item => item.category),
    )
    for (const category of ['acceptance', 'tests', 'build', 'typecheck', 'lint']) {
      if (!broadCategories.has(category)) {
        reasons.push(`UltraCheck omitted broad check category: ${category}`)
      }
    }
    if (result.broadChecks.some(
      item => !String(item.evidence || '').trim(),
    )) {
      reasons.push('UltraCheck broad check has no evidence')
    }
    if (
      !result.cleanRerun.performed
      || !String(result.cleanRerun.evidence || '').trim()
    ) {
      reasons.push('UltraCheck clean-process rerun is missing evidence')
    }
    if (result.hypotheses.length < 5) {
      reasons.push('UltraCheck contains fewer than five refutation hypotheses')
    }
    if (result.hypotheses.some(item => (
      !String(item.hypothesis || '').trim()
      || !String(item.test || '').trim()
      || !String(item.evidence || '').trim()
    ))) {
      reasons.push('UltraCheck hypothesis is incomplete or lacks evidence')
    }
    const hostileCategories = new Set(
      result.hostileInputs.map(item => item.category),
    )
    for (const category of [
      'empty',
      'null',
      'zero',
      'negative',
      'huge',
      'malformed',
      'unicode',
      'duplicate',
      'error-path',
      'boundary',
    ]) {
      if (!hostileCategories.has(category)) {
        reasons.push(`UltraCheck omitted hostile input category: ${category}`)
      }
    }
    if (result.hostileInputs.some(
      item => !String(item.evidence || '').trim(),
    )) {
      reasons.push('UltraCheck hostile-input result has no evidence')
    }
    if (
      result.evidenceLedger.length === 0
      || result.evidenceLedger.some(item => (
        !String(item.claim || '').trim()
        || !Array.isArray(item.evidence)
        || item.evidence.length === 0
        || item.evidence.some(value => !String(value || '').trim())
      ))
    ) {
      reasons.push('UltraCheck claim-level evidence ledger is incomplete')
    }
  }
  return Array.from(new Set(reasons))
}

function isAbortError(error) {
  const name = error && typeof error === 'object' && 'name' in error
    ? String(error.name)
    : ''
  const code = error && typeof error === 'object' && 'code' in error
    ? String(error.code)
    : ''
  const message = error && typeof error === 'object' && 'message' in error
    ? String(error.message)
    : String(error)
  return /abort|cancel|WorkflowAgentCapError|WorkflowBudgetExceededError/i.test(name)
    || /abort|cancel/i.test(code)
    || /\b(user cancel|workflow (?:abort|cancel|stop)|workflow agent\(\) call cap reached|workflow token budget exceeded|budget (?:limits?|exhaust(?:ed|ion)?|exceed(?:ed|s)?)|turn (?:cap|limit))\b/i.test(message)
}

function agentFailureReason(error) {
  const rendered = error && typeof error === 'object' && 'message' in error
    ? String(error.message)
    : String(error)
  return `agent call failed: ${rendered.slice(0, 500)}`
}

function providerFailureReason(result) {
  if (!result || result.status !== 'failed') return ''
  return String(result.summary || 'worker reported provider failure')
    .trim()
    .slice(0, 500)
}

const executionBudget = `EXECUTION BUDGET:
- Before each tool call, identify the exact unresolved acceptance criterion it tests.
- Do not retry a failed, timed-out, or zero-signal machine check more than once.
- After a second no-signal result, stop testing and return the strongest supported
  result, marking unresolved claims blocked with the smallest next action.
- Keep any shell command's combined declared worst-case runtime below 90 seconds.
- Existing direct evidence may be reused only after independently inspecting it;
  do not rerun an expensive check merely to reproduce already-corroborated evidence.`

async function dispatch(
  persona,
  objective,
  evidence,
  phaseName,
  suffix = '',
  round = 1,
  schema = workerSchema,
) {
  const queueItem = enqueue(persona, phaseName, objective, round)
  const attempts = routes(persona)
  for (let attempt = 0; attempt < attempts.length; attempt++) {
    const selected = attempts[attempt]
    queueItem.model = selected.model
    queueItem.attemptedModels.push(selected.model)
    updateQueue(queueItem, 'running')
    const prompt = `PERSONA: ${persona}
ROUTED MODEL: ${selected.model}
ROUTE ATTEMPT: ${attempt + 1}/${attempts.length}
WORKSPACE: ${workspace}
BEADS TRACKING:
${tracking ? excerpt(tracking, 4000) : 'No Bead is attached.'}

TASK:
${task}

AUTHORIZATION AND SCOPE:
${authorization}

ACCEPTANCE CRITERIA:
${acceptance.length
  ? acceptance.map((item, index) => `${index + 1}. ${item}`).join('\n')
  : 'No explicit criteria were supplied. Report this as unresolved.'}

PERSONA CONTRACT:
${personaPrompts[persona]}

VERIFICATION MODE:
${ultracheck
  ? 'ULTRACHECK: broad checks, clean rerun, hostile inputs, refutation hypotheses, and a claim-level evidence ledger are mandatory.'
  : 'Normal evidence-gated verification.'}

${executionBudget}

OBJECTIVE:
${objective}

EVIDENCE FROM PRIOR QUEUE UNITS:
${excerpt(evidence || 'No prior phase evidence.')}

Return the requested structured result. A successful tool exit is evidence only;
it does not establish task completion. Never invent a command, output, source,
artifact, or evidence identifier. Include every evidence identifier cited by a
supported claim in this result's own evidence inventory.`
    let result = null
    try {
      result = await agent(prompt, {
        label: `${persona}${suffix}${attempt ? `-fallback${attempt}` : ''}`,
        phase: phaseName,
        agentType: selected.agentType,
        schema,
      })
    } catch (error) {
      if (isAbortError(error)) throw error
      const reason = agentFailureReason(error)
      queueItem.routeAttempts.push({
        model: selected.model,
        outcome: 'unavailable',
        reasons: [reason],
      })
      log(
        `${queueItem.id}: ${selected.model} unavailable: ${reason}; `
        + 'trying declared fallback',
      )
      continue
    }
    const providerFailure = providerFailureReason(result)
    if (providerFailure) {
      queueItem.routeAttempts.push({
        model: selected.model,
        outcome: 'unavailable',
        reasons: [providerFailure],
      })
      log(
        `${queueItem.id}: ${selected.model} reported provider failure: `
        + `${providerFailure}; trying declared fallback`,
      )
      continue
    }
    const isUltraResult = schema === ultraSchema
    const validResult = isUltraResult
      ? validUltraResult(result)
      : validWorkerResult(result)
    if (validResult) {
      const degradationReasons = isUltraResult
        ? ultraDegradationReasons(result)
        : workerDegradationReasons(result, persona)
      if (degradationReasons.length) {
        queueItem.routeAttempts.push({
          model: selected.model,
          outcome: 'degraded',
          reasons: degradationReasons,
        })
        queueItem.degradationReasons.push(...degradationReasons)
        log(
          `${queueItem.id}: ${selected.model} response degraded: `
          + `${degradationReasons.join('; ')}; trying declared fallback`,
        )
        continue
      }
      queueItem.routeAttempts.push({
        model: selected.model,
        outcome: 'usable',
        reasons: [],
      })
      updateQueue(queueItem, result.status === 'blocked' ? 'blocked' : 'returned', {
        summary: result.summary,
        workerStatus: result.status,
      })
      return result
    }
    queueItem.routeAttempts.push({
      model: selected.model,
      outcome: 'invalid',
      reasons: ['missing or invalid structured result'],
    })
    log(
      `${queueItem.id}: ${selected.model} returned no valid result; trying declared fallback`,
    )
  }
  updateQueue(queueItem, 'blocked', {
    reason: 'all declared routes returned an invalid or unavailable result',
  })
  return {
    status: 'blocked',
    summary: 'All declared routes returned an invalid or unavailable result.',
    claims: [],
    evidence: [],
    checks: [],
    unresolved: ['No valid worker result was available.'],
    nextActions: ['Inspect the failed route and retry this queue unit.'],
  }
}

function ultraGate(report) {
  if (!report || report.status !== 'completed') {
    return { passed: false, blockers: ['UltraCheck refutation did not complete.'] }
  }
  const blockers = []
  const broadCategories = new Set(
    Array.isArray(report.broadChecks)
      ? report.broadChecks.map(item => item.category)
      : [],
  )
  for (const category of ['acceptance', 'tests', 'build', 'typecheck', 'lint']) {
    if (!broadCategories.has(category)) {
      blockers.push(`UltraCheck omitted broad check category: ${category}`)
    }
  }
  const failedBroad = (report.broadChecks || []).filter(
    item => item.applicable && item.status !== 'passed',
  )
  if (failedBroad.length) {
    blockers.push('One or more applicable broad checks did not pass.')
  }
  if (
    !report.cleanRerun
    || !report.cleanRerun.performed
    || report.cleanRerun.status !== 'passed'
    || !String(report.cleanRerun.evidence || '').trim()
  ) {
    blockers.push('A passing clean-process rerun with evidence is missing.')
  }
  if (!Array.isArray(report.hypotheses) || report.hypotheses.length < 5) {
    blockers.push('Fewer than five independent refutation hypotheses were tested.')
  }
  const hostileCategories = new Set(
    Array.isArray(report.hostileInputs)
      ? report.hostileInputs.map(item => item.category)
      : [],
  )
  for (const category of [
    'empty',
    'null',
    'zero',
    'negative',
    'huge',
    'malformed',
    'unicode',
    'duplicate',
    'error-path',
    'boundary',
  ]) {
    if (!hostileCategories.has(category)) {
      blockers.push(`UltraCheck omitted hostile input category: ${category}`)
    }
  }
  const failedHostile = (report.hostileInputs || []).filter(
    item => item.applicable && item.status !== 'passed',
  )
  if (failedHostile.length) {
    blockers.push('One or more applicable hostile-input checks did not pass.')
  }
  if (
    !Array.isArray(report.evidenceLedger)
    || report.evidenceLedger.length === 0
    || report.evidenceLedger.some(
      item => item.status !== 'supported' || !item.evidence.length,
    )
  ) {
    blockers.push('The claim-level evidence ledger is empty or unresolved.')
  }
  return { passed: blockers.length === 0, blockers }
}

function enforceJudgment(raw, ultraResult) {
  const judgment = raw && typeof raw === 'object'
    ? raw
    : {
      decision: 'inconclusive',
      summary: 'No valid judge result was available.',
      criteria: [],
      completionClaims: [],
      blockers: ['No independent judge result was available.'],
      nextActions: ['Inspect judge route failures.'],
      progress: {
        artifactChanged: false,
        newEvidence: false,
        newChecks: false,
      },
    }
  judgment.blockers = Array.isArray(judgment.blockers)
    ? judgment.blockers.map(String)
    : []
  judgment.nextActions = Array.isArray(judgment.nextActions)
    ? judgment.nextActions.map(String)
    : []
  const rows = Array.isArray(judgment.criteria) ? judgment.criteria : []
  const criteriaComplete = acceptance.length > 0
    && rows.length === acceptance.length
    && rows.every((row, index) => (
      String(row.criterion || '').trim() === acceptance[index]
      && row.status === 'passed'
      && Array.isArray(row.evidence)
      && row.evidence.some(item => String(item).trim())
    ))
  if (judgment.decision === 'accept' && !criteriaComplete) {
    judgment.decision = 'revise'
    judgment.blockers.push(
      'Deterministic gate rejected acceptance: exact criterion-level passing evidence is incomplete.',
    )
  }
  if (
    judgment.decision === 'accept'
    && (
      !Array.isArray(judgment.completionClaims)
      || judgment.completionClaims.some(
        claim => (
          claim.status !== 'supported'
          || !Array.isArray(claim.evidence)
          || claim.evidence.length === 0
        ),
      )
    )
  ) {
    judgment.decision = 'revise'
    judgment.blockers.push(
      'Deterministic gate rejected acceptance: a completion claim is unsupported.',
    )
  }
  if (judgment.decision === 'accept' && judgment.blockers.length) {
    judgment.decision = 'revise'
  }
  if (ultracheck) {
    const gate = ultraGate(ultraResult)
    if (!gate.passed && judgment.decision === 'accept') {
      judgment.decision = 'revise'
    }
    judgment.blockers.push(...gate.blockers)
  }
  judgment.blockers = Array.from(new Set(judgment.blockers))
  return judgment
}

function evidenceSignature(judgment) {
  const rows = Array.isArray(judgment.criteria) ? judgment.criteria : []
  return JSON.stringify(
    rows.map(row => ({
      criterion: String(row.criterion || '').trim(),
      status: row.status,
      evidence: Array.isArray(row.evidence)
        ? row.evidence.map(String).map(item => item.trim()).sort()
        : [],
    })),
  )
}

async function judgeRound(round, evidence) {
  const queueItem = enqueue(
    'judge',
    'Judgment',
    'Resolve exact acceptance criteria against independent evidence.',
    round,
  )
  const attempts = routes('judge')
  let raw = null
  for (let attempt = 0; attempt < attempts.length && !raw; attempt++) {
    const selected = attempts[attempt]
    queueItem.model = selected.model
    queueItem.attemptedModels.push(selected.model)
    updateQueue(queueItem, 'running')
    let candidate = null
    try {
      candidate = await agent(`PERSONA: judge
ROUTED MODEL: ${selected.model}
ROUTE ATTEMPT: ${attempt + 1}/${attempts.length}
WORKSPACE: ${workspace}
TASK:
${task}

AUTHORIZATION AND SCOPE:
${authorization}

EXACT ACCEPTANCE CRITERIA:
${acceptance.length
  ? acceptance.map((item, index) => `${index + 1}. ${item}`).join('\n')
  : 'No explicit criteria were supplied; acceptance is forbidden.'}

EVIDENCE:
${excerpt(evidence, 32000)}

NATIVE QUEUE SNAPSHOT:
${excerpt(queueSnapshot(), 12000)}

${executionBudget}

Return one criteria row for every criterion, in the same order and with the
exact criterion text. A worker returning, editing a file, or exiting zero does
not prove completion. Accept only direct artifact evidence or reproducible
machine evidence. The queue snapshot is workflow-owned state, not a worker
claim. Progress booleans compare this round with the prior round.`, {
      label: `judge-r${round}${attempt ? `-fallback${attempt}` : ''}`,
      phase: 'Judgment',
      agentType: selected.agentType,
      schema: judgeSchema,
      })
    } catch (error) {
      if (isAbortError(error)) throw error
      const reason = agentFailureReason(error)
      queueItem.routeAttempts.push({
        model: selected.model,
        outcome: 'unavailable',
        reasons: [reason],
      })
      log(
        `${queueItem.id}: ${selected.model} unavailable: ${reason}; `
        + 'trying declared fallback',
      )
      continue
    }
    const providerFailure = providerFailureReason(candidate)
    if (providerFailure) {
      queueItem.routeAttempts.push({
        model: selected.model,
        outcome: 'unavailable',
        reasons: [providerFailure],
      })
      log(
        `${queueItem.id}: ${selected.model} judge provider failure: `
        + `${providerFailure}; trying declared fallback`,
      )
      continue
    }
    if (validJudgeResult(candidate)) {
      const degradationReasons = judgeDegradationReasons(candidate)
      if (degradationReasons.length) {
        queueItem.routeAttempts.push({
          model: selected.model,
          outcome: 'degraded',
          reasons: degradationReasons,
        })
        queueItem.degradationReasons.push(...degradationReasons)
        log(
          `${queueItem.id}: ${selected.model} judgment degraded: `
          + `${degradationReasons.join('; ')}; trying declared fallback`,
        )
      } else {
        queueItem.routeAttempts.push({
          model: selected.model,
          outcome: 'usable',
          reasons: [],
        })
        raw = candidate
      }
    } else {
      queueItem.routeAttempts.push({
        model: selected.model,
        outcome: 'invalid',
        reasons: ['missing or invalid structured judgment'],
      })
      log(
        `${queueItem.id}: ${selected.model} returned an invalid judgment; trying fallback`,
      )
    }
  }
  if (raw) {
    updateQueue(queueItem, 'returned', { summary: raw.summary })
  } else {
    updateQueue(queueItem, 'blocked', {
      reason: 'all declared judge routes returned no result',
    })
  }
  return raw
}

phase('Opening posts')
const opening = quick
  ? [await dispatch(
    'researcher',
    'Build the evidence inventory before conclusions harden.',
    null,
    'Opening posts',
  )]
  : await parallel([
    () => dispatch(
      'researcher',
      'Build the evidence inventory before conclusions harden.',
      null,
      'Opening posts',
    ),
    () => dispatch(
      'bullshitter',
      'Independently challenge the likely conclusions and identify evidence gaps or cheaper falsification tests without treating hypotheses as facts.',
      null,
      'Opening posts',
    ),
  ])

phase('Cross-examination')
const cross = fullForum
  ? await parallel([
    () => dispatch(
      'exploiter',
      'Cross-examine the opening posts and produce a precise, scope-bounded technical analysis.',
      { opening },
      'Cross-examination',
    ),
    () => dispatch(
      'verifier',
      'Attack the opening posts for unsupported claims, missing evidence, and cheaper falsification tests.',
      { opening },
      'Cross-examination',
      '-opening',
    ),
  ])
  : []

phase('Artifact workshop')
let artifact = await dispatch(
  'engineer',
  'Use the strongest surviving claims to implement or construct the requested artifact. Do not repeat expensive checks already established by direct opening evidence; run only the smallest missing or artifact-specific check. The verification phase owns independent re-runs.',
  { opening, cross },
  'Artifact workshop',
)

async function verifyAndJudge(round, artifactValue) {
  phase('Verification')
  const verification = quick
    ? [await dispatch(
      'verifier',
      'Independently inspect the artifact and attempt to falsify every material completion claim.',
      { opening, cross, artifact: artifactValue },
      'Verification',
      `-artifact-r${round}`,
      round,
    )]
    : await parallel([
      () => dispatch(
        'verifier',
        'Independently inspect the artifact and attempt to falsify every material completion claim.',
        { opening, cross, artifact: artifactValue },
        'Verification',
        `-artifact-r${round}`,
        round,
      ),
      () => dispatch(
        'researcher',
        'Check whether the artifact and citations cover the original evidence base without omissions or drift.',
        { opening, cross, artifact: artifactValue },
        'Verification',
        `-coverage-r${round}`,
        round,
      ),
    ])
  const refutation = ultracheck
    ? await dispatch(
      'verifier',
      'Execute the complete UltraCheck refutation contract. Record all five broad-check categories and all ten hostile-input categories, marking a category not applicable only with a concrete reason.',
      { opening, cross, artifact: artifactValue, verification },
      'Verification',
      `-ultracheck-r${round}`,
      round,
      ultraSchema,
    )
    : null

  phase('Judgment')
  const rawJudgment = await judgeRound(
    round,
    { opening, cross, artifact: artifactValue, verification, refutation },
  )
  const judgment = enforceJudgment(rawJudgment, refutation)
  return { verification, refutation, judgment }
}

let reviewed = await verifyAndJudge(1, artifact)
let round = 1
let previousSignature = null
let stalledRounds = 0
let stopReason = ''

while (reviewed.judgment.decision !== 'accept') {
  const decision = reviewed.judgment.decision
  if (decision === 'reject') {
    stopReason = 'rejected'
    break
  }
  const actionable = reviewed.judgment.nextActions.length > 0
  if (decision === 'inconclusive' && !actionable) {
    stopReason = 'inconclusive'
    break
  }

  const signature = evidenceSignature(reviewed.judgment)
  const progress = reviewed.judgment.progress || {}
  const claimedProgress = Boolean(
    progress.artifactChanged || progress.newEvidence || progress.newChecks,
  )
  if (previousSignature !== null && (
    signature === previousSignature || !claimedProgress
  )) {
    stalledRounds += 1
  } else {
    stalledRounds = 0
  }
  previousSignature = signature
  if (stalledRounds >= noProgressLimit) {
    reviewed.judgment.decision = 'inconclusive'
    reviewed.judgment.blockers.push(
      `No criterion-level evidence progress for ${stalledRounds} consecutive rounds.`,
    )
    stopReason = 'no-progress'
    break
  }
  if (round >= maxRounds) {
    reviewed.judgment.decision = 'inconclusive'
    reviewed.judgment.blockers.push(
      `Native workflow exhausted its ${maxRounds}-round budget.`,
    )
    stopReason = 'round-limit'
    break
  }

  round += 1
  phase('Revision')
  artifact = await dispatch(
    'engineer',
    `Resolve only the queued judge blockers and next actions for round ${round}.
Blockers:
${reviewed.judgment.blockers.map(item => `- ${item}`).join('\n')}
Next actions:
${reviewed.judgment.nextActions.map(item => `- ${item}`).join('\n')}`,
    {
      priorArtifact: artifact,
      verification: reviewed.verification,
      refutation: reviewed.refutation,
      judgment: reviewed.judgment,
    },
    'Revision',
    `-revision-r${round}`,
    round,
  )
  reviewed = await verifyAndJudge(round, artifact)
}

if (reviewed.judgment.decision === 'accept') {
  stopReason = 'accepted'
}

for (const item of queue) {
  if (item.status === 'returned') {
    item.status = reviewed.judgment.decision === 'accept'
      ? 'accepted'
      : 'verified'
  }
}

return {
  workflowRunId,
  mode,
  quick,
  fullForum,
  status: reviewed.judgment.decision === 'accept' ? 'accepted' : 'blocked',
  stopReason,
  rounds: round,
  task,
  workspace,
  tracking,
  routes: assignments,
  queue,
  opening,
  crossExamination: cross,
  artifact,
  verification: reviewed.verification,
  refutation: reviewed.refutation,
  judgment: reviewed.judgment,
}
