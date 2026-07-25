export const meta = {
  name: 'fugu-sweep-final',
  description: 'Read-only independent audit and exact acceptance gate for an integrated Fugu sweep',
  phases: [
    { title: 'Independent audit', detail: 'artifact and coverage verification' },
    { title: 'Judgment', detail: 'exact criterion-level decision' },
  ],
}

let input = {}
if (args && typeof args === 'object') {
  input = args
} else if (typeof args === 'string' && args.trim()) {
  try {
    input = JSON.parse(args)
  } catch {
    return { status: 'rejected', reason: 'fugu-sweep-final args must be valid JSON' }
  }
}

const task = String(input.task || '').trim()
const workspace = String(input.workspace || '').trim()
const workflowRunId = String(input.workflowRunId || '').trim()
const revisionRound = Number(input.revisionRound || 0)
const acceptance = Array.isArray(input.acceptanceCriteria)
  ? input.acceptanceCriteria.map(String).map(item => item.trim()).filter(Boolean)
  : []
if (!task || !workspace || !workflowRunId || !acceptance.length) {
  return {
    status: 'rejected',
    reason: 'fugu-sweep-final requires task, workspace, workflowRunId, and acceptanceCriteria',
  }
}
if (!Number.isInteger(revisionRound) || revisionRound < 0 || revisionRound > 1) {
  return {
    status: 'rejected',
    reason: 'fugu-sweep-final revisionRound must be 0 or 1',
  }
}

const authorization = String(
  input.authorization || 'No security authorization was supplied.',
)
const assignments = Array.isArray(input.assignments) ? input.assignments : []
const routeByPersona = Object.fromEntries(
  assignments.map(item => [String(item.persona), item]),
)
const plan = input.plan && typeof input.plan === 'object' ? input.plan : {}
const ownerResults = Array.isArray(input.ownerResults) ? input.ownerResults : []
const reviewResults = Array.isArray(input.reviewResults) ? input.reviewResults : []
const integrationResult = input.integrationResult
  && typeof input.integrationResult === 'object'
  ? input.integrationResult
  : {}

function excerpt(value, limit = 18000) {
  const rendered = typeof value === 'string' ? value : JSON.stringify(value)
  return rendered.length <= limit
    ? rendered
    : `${rendered.slice(0, limit)}\n[truncated by workflow]`
}

function isCodexRoute(model) {
  return model === 'gpt-5.6-sol' || model.startsWith('codex-sol-')
}

function agentTypeForModel(model) {
  if (model.startsWith('fable-5')) return 'orchestrator:fable-neutral'
  if (isCodexRoute(model)) return 'orchestrator:codex-worker'
  if (model.startsWith('opus-4.8')) return 'orchestrator:opus-48-recovery'
  return 'orchestrator:opus-worker'
}

function routes(persona, preferredFamily) {
  const selected = routeByPersona[persona] || {}
  const candidates = Array.from(new Set([
    String(selected.model || 'opus-5-bounded'),
    ...(Array.isArray(selected.fallback_order)
      ? selected.fallback_order.map(String)
      : []),
    'opus-5-bounded',
    'codex-sol-high',
    'gpt-5.6-sol',
    'opus-4.8-bounded',
  ]))
  const eligible = candidates.filter(model => !model.startsWith('fable-5'))
  const preferred = eligible.filter(model => (
    preferredFamily === 'openai'
      ? isCodexRoute(model)
      : !isCodexRoute(model)
  ))
  if (preferredFamily === 'openai') {
    preferred.sort((left, right) => (
      Number(right === 'codex-sol-high') - Number(left === 'codex-sol-high')
    ))
  }
  const remainder = eligible.filter(model => !preferred.includes(model))
  return [...preferred, ...remainder].map(model => ({
    model,
    agentType: agentTypeForModel(model),
  }))
}

const criterionSchema = {
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
}

const auditSchema = {
  type: 'object',
  required: ['status', 'summary', 'criteria', 'findings', 'checks', 'unresolved'],
  properties: {
    status: { type: 'string', enum: ['completed', 'blocked', 'failed'] },
    summary: { type: 'string' },
    criteria: { type: 'array', items: criterionSchema },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'finding', 'evidence'],
        properties: {
          severity: {
            type: 'string',
            enum: ['critical', 'high', 'medium', 'low', 'none'],
          },
          finding: { type: 'string' },
          evidence: { type: 'array', items: { type: 'string' } },
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
          status: {
            type: 'string',
            enum: ['passed', 'failed', 'errored', 'not-run', 'not-applicable'],
          },
          evidence: { type: 'string' },
        },
      },
    },
    unresolved: { type: 'array', items: { type: 'string' } },
  },
}

const judgeSchema = {
  type: 'object',
  required: ['decision', 'summary', 'criteria', 'blockers', 'nextActions'],
  properties: {
    decision: {
      type: 'string',
      enum: ['accept', 'revise', 'reject', 'inconclusive'],
    },
    summary: { type: 'string' },
    criteria: { type: 'array', items: criterionSchema },
    blockers: { type: 'array', items: { type: 'string' } },
    nextActions: { type: 'array', items: { type: 'string' } },
  },
}

function criterionErrors(rows, source) {
  const errors = []
  if (!Array.isArray(rows) || rows.length !== acceptance.length) {
    return [`${source} did not return every exact acceptance criterion`]
  }
  rows.forEach((row, index) => {
    const criterion = String(row.criterion || '')
      .trim()
      .replace(/^\d+[.)]\s+/, '')
    if (criterion !== acceptance[index]) {
      errors.push(`${source} changed acceptance criterion ${index + 1}`)
    }
    if (row.status !== 'passed') {
      errors.push(`${source} did not pass criterion ${index + 1}`)
    }
    if (
      !Array.isArray(row.evidence)
      || !row.evidence.length
      || row.evidence.some(item => !String(item || '').trim())
    ) {
      errors.push(`${source} has no evidence for criterion ${index + 1}`)
    }
  })
  return errors
}

function uniqueStrings(values) {
  return Array.from(new Set(
    values.map(value => String(value || '').trim()).filter(Boolean),
  ))
}

function buildRevisionPacket(criteria, auditResults, judge, integration) {
  const failedCriteria = []
  criteria.forEach((criterion, index) => {
    const sources = []
    auditResults.forEach((result, auditIndex) => {
      const row = Array.isArray(result?.criteria)
        ? result.criteria[index]
        : null
      sources.push({
        source: `audit-${auditIndex + 1}`,
        status: String(row?.status || 'missing'),
        evidence: uniqueStrings(Array.isArray(row?.evidence) ? row.evidence : []),
      })
    })
    const judgeRow = Array.isArray(judge?.criteria)
      ? judge.criteria[index]
      : null
    sources.push({
      source: 'judge',
      status: String(judgeRow?.status || 'missing'),
      evidence: uniqueStrings(
        Array.isArray(judgeRow?.evidence) ? judgeRow.evidence : [],
      ),
    })
    if (sources.some(source => (
      source.status !== 'passed' || !source.evidence.length
    ))) {
      failedCriteria.push({ index, criterion, sources })
    }
  })

  const findings = []
  const failedChecks = []
  auditResults.forEach((result, auditIndex) => {
    for (const item of result?.findings || []) {
      if (!['critical', 'high'].includes(item.severity)) continue
      findings.push({
        source: `audit-${auditIndex + 1}`,
        severity: String(item.severity),
        finding: String(item.finding || '').trim(),
        evidence: uniqueStrings(
          Array.isArray(item.evidence) ? item.evidence : [],
        ),
      })
    }
    for (const item of result?.checks || []) {
      if (!['failed', 'errored'].includes(item.status)) continue
      failedChecks.push({
        source: `audit-${auditIndex + 1}`,
        name: String(item.name || '').trim(),
        status: String(item.status),
        evidence: String(item.evidence || '').trim(),
      })
    }
  })

  const integrationBlockers = []
  if (!['completed', 'accepted'].includes(integration?.status)) {
    integrationBlockers.push(...uniqueStrings([
      integration?.summary,
      integration?.reason,
      integration?.stopReason,
      ...(Array.isArray(integration?.unresolved) ? integration.unresolved : []),
    ]))
  }

  return {
    failedCriteria,
    findings,
    failedChecks,
    integrationBlockers,
    judgeBlockers: uniqueStrings(
      Array.isArray(judge?.blockers) ? judge.blockers : [],
    ),
    nextActions: uniqueStrings(
      Array.isArray(judge?.nextActions) ? judge.nextActions : [],
    ),
  }
}

const evidencePacket = {
  plan,
  ownerResults,
  reviewResults,
  integrationResult,
}
const acceptanceText = acceptance
  .map((item, index) => `CRITERION[${index}]=${JSON.stringify(item)}`)
  .join('\n')

async function audit(persona, objective, label, preferredFamily) {
  const attempts = routes(persona, preferredFamily)
  for (let index = 0; index < attempts.length; index++) {
    const selected = attempts[index]
    let result = null
    try {
      result = await agent(`READ-ONLY FINAL SWEEP AUDIT
PERSONA: ${persona}
ROUTED MODEL: ${selected.model}
ROUTE ATTEMPT: ${index + 1}/${attempts.length}
WORKFLOW RUN: ${workflowRunId}
WORKSPACE: ${workspace}

TASK:
${task}

AUTHORIZATION AND TARGET BOUNDARY:
${authorization}

EXACT ACCEPTANCE CRITERIA:
${acceptanceText}

OBJECTIVE:
${objective}

SWEEP EVIDENCE:
${excerpt(evidencePacket)}

Inspect the resulting main checkout directly. Do not edit, commit, push, launch
another workflow, or trust a worker's success label. Run only bounded read-only
checks needed to falsify material claims. Return every exact acceptance
criterion in the original order. A passed criterion requires concrete artifact
or command evidence.`, {
        label: `${label}${index ? `-fallback${index}` : ''}`,
        phase: 'Independent audit',
        agentType: selected.agentType,
        schema: auditSchema,
      })
    } catch (error) {
      log(`${label}: ${selected.model} unavailable; trying fallback`)
      continue
    }
    if (
      result
      && ['completed', 'blocked'].includes(result.status)
      && Array.isArray(result.criteria)
      && Array.isArray(result.findings)
      && Array.isArray(result.checks)
      && Array.isArray(result.unresolved)
    ) {
      return { ...result, routedModel: selected.model }
    }
    log(`${label}: ${selected.model} returned no usable audit; trying fallback`)
  }
  return {
    status: 'failed',
    summary: 'Every declared audit route was unavailable or malformed.',
    criteria: [],
    findings: [],
    checks: [],
    unresolved: ['No usable audit result was returned.'],
    routedModel: null,
  }
}

phase('Independent audit')
const audits = await parallel([
  () => audit(
    'verifier',
    'Adversarially inspect the integrated artifact, rerun decisive checks, and identify regressions, hostile boundary failures, or unsupported completion claims.',
    'sweep-artifact-verifier',
    'openai',
  ),
  () => audit(
    'researcher',
    'Independently check scope coverage, omissions, dependency integration, and whether the evidence actually supports the original task.',
    'sweep-coverage-verifier',
    'anthropic',
  ),
])

phase('Judgment')
let judgment = null
for (const [index, judgeRoute] of routes('judge', 'anthropic').entries()) {
  try {
    const candidate = await agent(`READ-ONLY FINAL SWEEP JUDGE
ROUTED MODEL: ${judgeRoute.model}
ROUTE ATTEMPT: ${index + 1}
WORKFLOW RUN: ${workflowRunId}
WORKSPACE: ${workspace}

TASK:
${task}

EXACT ACCEPTANCE CRITERIA:
${acceptanceText}

INTEGRATION RESULT:
${excerpt(integrationResult, 8000)}

INDEPENDENT AUDITS:
${excerpt(audits)}

Resolve every exact criterion in order. Worker and reviewer returns are
testimony, not proof. Accept only when integration completed, every criterion
has direct evidence, both independent audits support it, and no unresolved
critical or high finding remains. Do not edit or launch another workflow.`, {
      label: `sweep-final-judge${index ? `-fallback${index}` : ''}`,
      phase: 'Judgment',
      agentType: judgeRoute.agentType,
      schema: judgeSchema,
    })
    if (
      candidate
      && ['accept', 'revise', 'reject', 'inconclusive'].includes(
        candidate.decision,
      )
      && Array.isArray(candidate.criteria)
      && Array.isArray(candidate.blockers)
      && Array.isArray(candidate.nextActions)
    ) {
      judgment = { ...candidate, routedModel: judgeRoute.model }
      break
    }
  } catch (error) {
    log(`judge: ${judgeRoute.model} unavailable; trying fallback`)
  }
}

const gateErrors = []
if (!['completed', 'accepted'].includes(integrationResult.status)) {
  gateErrors.push('integration did not complete')
}
audits.forEach((result, index) => {
  const name = `audit ${index + 1}`
  if (!result || result.status !== 'completed') {
    gateErrors.push(`${name} did not complete`)
    return
  }
  gateErrors.push(...criterionErrors(result.criteria, name))
  if ((result.findings || []).some(item => (
    ['critical', 'high'].includes(item.severity)
  ))) {
    gateErrors.push(`${name} has an unresolved critical or high finding`)
  }
  if ((result.checks || []).some(item => (
    ['failed', 'errored'].includes(item.status)
  ))) {
    gateErrors.push(`${name} has a failed or errored check`)
  }
})
if (!judgment || judgment.decision !== 'accept') {
  gateErrors.push('judge did not accept')
} else {
  gateErrors.push(...criterionErrors(judgment.criteria, 'judge'))
  if ((judgment.blockers || []).length) gateErrors.push('judge reported blockers')
}

const blocked = gateErrors.length > 0
const revisionPacket = blocked
  ? buildRevisionPacket(acceptance, audits, judgment, integrationResult)
  : null

return {
  workflowRunId,
  status: blocked ? 'blocked' : 'accepted',
  stopReason: blocked
    ? (
      revisionRound === 0
        ? 'final-audit-failed'
        : 'final-audit-failed-after-remediation'
    )
    : 'accepted',
  revisionRound,
  remediationAllowed: blocked && revisionRound === 0,
  revisionPacket,
  audits,
  judgment,
  gateErrors: Array.from(new Set(gateErrors)),
  integrationResult,
}
