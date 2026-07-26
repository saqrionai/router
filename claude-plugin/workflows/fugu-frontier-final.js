export const meta = {
  name: 'fugu-frontier-final',
  description: 'Parallel independent criterion checks and deterministic acceptance for at most two integrated frontier Beads',
  phases: [
    { title: 'Independent checks', detail: 'falsify each Bead against the resulting checkout' },
    { title: 'Acceptance gate', detail: 'resolve exact criteria without another model panel' },
  ],
}

let input = {}
if (args && typeof args === 'object') {
  input = args
} else if (typeof args === 'string' && args.trim()) {
  try {
    input = JSON.parse(args)
  } catch {
    return { status: 'rejected', reason: 'fugu-frontier-final args must be valid JSON' }
  }
}

const workspace = String(input.workspace || '').trim()
const items = Array.isArray(input.items) ? input.items : []
const integrationResult = input.integrationResult
  && typeof input.integrationResult === 'object'
  ? input.integrationResult
  : {}
if (!workspace || !items.length || items.length > 2) {
  return {
    status: 'rejected',
    reason: 'fugu-frontier-final requires workspace and one or two items',
  }
}

function excerpt(value, limit = 12000) {
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

function checkerRoute(item) {
  const assignments = Array.isArray(item.assignments) ? item.assignments : []
  const verifier = assignments.find(candidate => candidate.persona === 'verifier') || {}
  const candidates = Array.from(new Set([
    String(verifier.model || 'opus-5-bounded'),
    ...(Array.isArray(verifier.fallback_order)
      ? verifier.fallback_order.map(String)
      : []),
    'opus-5-bounded',
  ]))
  const eligible = Boolean(item.securityTask)
    ? candidates.filter(model => !model.startsWith('fable-5'))
    : candidates
  const model = eligible[0] || 'opus-5-bounded'
  return { model, agentType: agentTypeForModel(model) }
}

const checkerSchema = {
  type: 'object',
  required: ['status', 'summary', 'criteria', 'checks', 'blockers', 'nextActions'],
  properties: {
    status: { type: 'string', enum: ['completed', 'blocked', 'failed'] },
    summary: { type: 'string' },
    criteria: {
      type: 'array',
      items: {
        type: 'object',
        required: ['criterion', 'status', 'evidence'],
        properties: {
          criterion: { type: 'string' },
          status: { type: 'string', enum: ['passed', 'failed', 'unverified'] },
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
    blockers: { type: 'array', items: { type: 'string' } },
    nextActions: { type: 'array', items: { type: 'string' } },
  },
}

function criterionErrors(criteria, expected) {
  if (!expected.length) return ['Bead has no acceptance criteria']
  if (!Array.isArray(criteria) || criteria.length !== expected.length) {
    return ['checker did not return every exact acceptance criterion']
  }
  const errors = []
  for (let index = 0; index < expected.length; index++) {
    const row = criteria[index] || {}
    if (String(row.criterion || '').trim() !== expected[index]) {
      errors.push(`criterion ${index + 1} changed or reordered`)
    }
    if (row.status !== 'passed') {
      errors.push(`criterion ${index + 1} is not passed`)
    }
    if (!Array.isArray(row.evidence) || !row.evidence.some(value => String(value).trim())) {
      errors.push(`criterion ${index + 1} lacks direct evidence`)
    }
  }
  return errors
}

async function checkItem(item, index) {
  const issueId = String(item.issueId || '').trim()
  const task = String(item.task || '').trim()
  const acceptance = Array.isArray(item.acceptanceCriteria)
    ? item.acceptanceCriteria.map(String).map(value => value.trim()).filter(Boolean)
    : []
  const route = checkerRoute(item)
  if (!issueId || !task) {
    return {
      issueId,
      route,
      result: null,
      infrastructureErrors: ['item requires issueId and task'],
    }
  }
  let result = null
  try {
    result = await agent(`READ-ONLY FRONTIER BEAD CHECKER
BEAD: ${issueId}
ROUTED MODEL: ${route.model}
WORKSPACE: ${workspace}

TASK:
${task}

EXACT ACCEPTANCE CRITERIA:
${acceptance.map((criterion, criterionIndex) => (
    `CRITERION[${criterionIndex}]=${JSON.stringify(criterion)}`
  )).join('\n') || 'No acceptance criteria were supplied.'}

OWNER RESULT:
${excerpt(item.ownerResult)}

SERIAL INTEGRATION RESULT:
${excerpt(integrationResult)}

Inspect the resulting main checkout directly. Do not edit, commit, launch
another workflow, or trust the owner's completion label. Run only the bounded
checks needed to falsify the exact criteria. Return every criterion exactly and
in order. A passed row requires direct artifact or reproducible command
evidence.`, {
      label: `frontier-check-${index + 1}-${issueId}`,
      phase: 'Independent checks',
      agentType: route.agentType,
      schema: checkerSchema,
    })
  } catch (error) {
    return {
      issueId,
      route,
      result: null,
      infrastructureErrors: [String(error?.message || error)],
    }
  }
  return { issueId, route, result, infrastructureErrors: [] }
}

phase('Independent checks')
const calls = items.map((item, index) => () => checkItem(item, index))
const checked = calls.length === 2
  ? await parallel(calls)
  : [await calls[0]()]

phase('Acceptance gate')
const results = checked.map((entry, index) => {
  const item = items[index]
  const acceptance = Array.isArray(item.acceptanceCriteria)
    ? item.acceptanceCriteria.map(String).map(value => value.trim()).filter(Boolean)
    : []
  const owner = item.ownerResult && typeof item.ownerResult === 'object'
    ? item.ownerResult
    : {}
  const result = entry.result && typeof entry.result === 'object'
    ? entry.result
    : {}
  const errors = [...entry.infrastructureErrors]
  if (owner.status !== 'completed') errors.push('owner did not complete')
  if (Boolean(item.writes)) {
    if (integrationResult.status !== 'completed') {
      errors.push('serial integration did not complete')
    }
    const commitSha = String(owner.commitSha || '')
    const integrated = Array.isArray(integrationResult.integratedCommits)
      ? integrationResult.integratedCommits.map(String)
      : []
    if (!commitSha || !integrated.includes(commitSha)) {
      errors.push('owner commit is not present in serial integration evidence')
    }
    if (!Array.isArray(owner.checks) || !owner.checks.length) {
      errors.push('writing owner returned no check evidence')
    } else if (owner.checks.some(check => (
      ['failed', 'errored', 'not-run'].includes(check.status)
    ))) {
      errors.push('writing owner has a failed, errored, or unrun check')
    }
  }
  if (result.status !== 'completed') errors.push('independent checker did not complete')
  errors.push(...criterionErrors(result.criteria, acceptance))
  if (Array.isArray(result.blockers) && result.blockers.length) {
    errors.push('independent checker returned blockers')
  }
  if (Array.isArray(result.checks) && result.checks.some(check => (
    ['failed', 'errored', 'not-run'].includes(check.status)
  ))) {
    errors.push('independent checker has a failed, errored, or unrun check')
  }
  return {
    issueId: entry.issueId,
    decision: errors.length ? 'revise' : 'accept',
    summary: String(result.summary || owner.summary || ''),
    errors: Array.from(new Set(errors)),
    route: entry.route,
    checker: result,
  }
})

return {
  status: results.every(result => result.decision === 'accept')
    ? 'accepted'
    : 'blocked',
  stopReason: results.every(result => result.decision === 'accept')
    ? 'accepted'
    : 'criterion-check-failed',
  workspace,
  integrationResult,
  results,
}
