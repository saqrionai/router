export const meta = {
  name: 'fugu-sweep',
  description: 'Read-only Fugu sweep planner with deterministic DAG, scope, concurrency, and risk-policy validation',
  phases: [
    { title: 'Plan', detail: 'inspect the repository and propose bounded units' },
    { title: 'Validate', detail: 'reject cycles, escaped paths, overlap, and missing checks' },
  ],
}

let input = {}
if (args && typeof args === 'object') {
  input = args
} else if (typeof args === 'string' && args.trim()) {
  try {
    input = JSON.parse(args)
  } catch {
    return { status: 'rejected', reason: 'fugu-sweep args must be valid JSON' }
  }
}

const task = String(input.task || '').trim()
const workspace = String(input.workspace || '').trim()
const workflowRunId = String(input.workflowRunId || '').trim()
if (!task || !workspace || !workflowRunId) {
  return {
    status: 'rejected',
    reason: 'fugu-sweep requires task, workspace, and workflowRunId',
  }
}

const authorization = String(
  input.authorization || 'No security authorization was supplied.',
)
const acceptance = Array.isArray(input.acceptanceCriteria)
  ? input.acceptanceCriteria.map(String).map(item => item.trim()).filter(Boolean)
  : []
const assignments = Array.isArray(input.assignments) ? input.assignments : []
const routeByPersona = Object.fromEntries(
  assignments.map(item => [String(item.persona), item]),
)
const tracking = input.tracking && typeof input.tracking === 'object'
  ? input.tracking
  : null
const maxUnits = Math.max(1, Math.min(Number(input.maxUnits || 64), 64))
const maxConcurrency = Math.max(
  1,
  Math.min(Number(input.maxConcurrency || 8), 12),
)
const securityTask = Boolean(input.securityTask)
const integrationChecks = Array.isArray(input.integrationChecks)
  ? input.integrationChecks.map(String).map(item => item.trim()).filter(Boolean)
  : []

const personas = new Set([
  'researcher',
  'bullshitter',
  'exploiter',
  'engineer',
  'verifier',
])
const risks = new Set(['low', 'medium', 'high', 'critical'])
const kinds = new Set(['research', 'implementation', 'test', 'artifact'])
const resources = new Set(['light', 'medium', 'heavy'])

const planSchema = {
  type: 'object',
  required: ['status', 'summary', 'baseSha', 'repoClean', 'units'],
  properties: {
    status: { type: 'string', enum: ['completed', 'blocked'] },
    summary: { type: 'string' },
    baseSha: { type: 'string' },
    repoClean: { type: 'boolean' },
    units: {
      type: 'array',
      minItems: 1,
      maxItems: 64,
      items: {
        type: 'object',
        required: [
          'id',
          'title',
          'objective',
          'kind',
          'writes',
          'risk',
          'resource',
          'persona',
          'paths',
          'dependsOn',
          'acceptanceCriteria',
          'checks',
        ],
        properties: {
          id: {
            type: 'string',
            pattern: '^[a-z0-9][a-z0-9._-]{0,63}$',
          },
          title: { type: 'string' },
          objective: { type: 'string' },
          kind: {
            type: 'string',
            enum: ['research', 'implementation', 'test', 'artifact'],
          },
          writes: { type: 'boolean' },
          risk: {
            type: 'string',
            enum: ['low', 'medium', 'high', 'critical'],
          },
          resource: {
            type: 'string',
            enum: ['light', 'medium', 'heavy'],
          },
          persona: {
            type: 'string',
            enum: [
              'researcher',
              'bullshitter',
              'exploiter',
              'engineer',
              'verifier',
            ],
          },
          paths: {
            type: 'array',
            items: {
              type: 'string',
              pattern: '^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!\\.git(?:/|$)).+',
            },
          },
          dependsOn: { type: 'array', items: { type: 'string' } },
          acceptanceCriteria: {
            type: 'array',
            minItems: 1,
            items: { type: 'string' },
          },
          checks: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

function normalPath(value) {
  return String(value || '').trim().replace(/^\.\//, '').replace(/\/+/g, '/')
}

function safePath(value) {
  const path = normalPath(value)
  return Boolean(
    path
      && !path.startsWith('/')
      && path !== '.'
      && path !== '..'
      && !path.split('/').includes('..')
      && path !== '.git'
      && !path.startsWith('.git/'),
  )
}

function scopeRoot(value) {
  return normalPath(value).replace(/\/\*\*?$/, '').replace(/\/$/, '')
}

function scopesOverlap(left, right) {
  const a = scopeRoot(left)
  const b = scopeRoot(right)
  return a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`)
}

function dependencyClosure(units, start) {
  const byId = new Map(units.map(unit => [unit.id, unit]))
  const seen = new Set()
  const pending = [...(byId.get(start)?.dependsOn || [])]
  while (pending.length) {
    const id = pending.pop()
    if (seen.has(id)) continue
    seen.add(id)
    pending.push(...(byId.get(id)?.dependsOn || []))
  }
  return seen
}

function validatePlan(plan) {
  const errors = []
  if (!plan || plan.status !== 'completed') {
    return ['planner did not complete']
  }
  if (!/^[0-9a-f]{7,64}$/i.test(String(plan.baseSha || ''))) {
    errors.push('baseSha is not a Git object ID')
  }
  if (!Array.isArray(plan.units) || !plan.units.length) {
    errors.push('plan contains no units')
    return errors
  }
  if (plan.units.length > maxUnits) {
    errors.push(`plan contains ${plan.units.length} units; maximum is ${maxUnits}`)
  }
  const ids = new Set()
  for (const unit of plan.units) {
    const id = String(unit.id || '')
    if (!/^[a-z0-9][a-z0-9._-]{0,63}$/.test(id)) {
      errors.push(`invalid unit id: ${id || '<empty>'}`)
    }
    if (ids.has(id)) errors.push(`duplicate unit id: ${id}`)
    ids.add(id)
    if (!String(unit.title || '').trim()) errors.push(`${id}: empty title`)
    if (!String(unit.objective || '').trim()) errors.push(`${id}: empty objective`)
    if (!kinds.has(unit.kind)) errors.push(`${id}: invalid kind`)
    if (!risks.has(unit.risk)) errors.push(`${id}: invalid risk`)
    if (!resources.has(unit.resource)) errors.push(`${id}: invalid resource`)
    if (!personas.has(unit.persona)) errors.push(`${id}: invalid owner persona`)
    if (typeof unit.writes !== 'boolean') errors.push(`${id}: writes must be boolean`)
    if (
      !Array.isArray(unit.acceptanceCriteria)
      || !unit.acceptanceCriteria.length
      || unit.acceptanceCriteria.some(item => !String(item).trim())
    ) {
      errors.push(`${id}: acceptance criteria are empty`)
    }
    if (!Array.isArray(unit.paths) || unit.paths.some(path => !safePath(path))) {
      errors.push(`${id}: unsafe or malformed path scope`)
    }
    if (unit.writes && unit.paths.length === 0) {
      errors.push(`${id}: a writing unit requires at least one path scope`)
    }
    if (unit.writes && (!Array.isArray(unit.checks) || !unit.checks.length)) {
      errors.push(`${id}: a writing unit requires at least one real check`)
    }
    if (!unit.writes && unit.paths.length) {
      errors.push(`${id}: a read-only unit cannot claim write paths`)
    }
  }
  for (const unit of plan.units) {
    for (const dependency of unit.dependsOn || []) {
      if (!ids.has(dependency)) {
        errors.push(`${unit.id}: unknown dependency ${dependency}`)
      }
      if (dependency === unit.id) errors.push(`${unit.id}: self dependency`)
    }
  }

  const indegree = new Map(plan.units.map(unit => [unit.id, 0]))
  const dependents = new Map(plan.units.map(unit => [unit.id, []]))
  for (const unit of plan.units) {
    for (const dependency of unit.dependsOn || []) {
      if (!ids.has(dependency)) continue
      indegree.set(unit.id, indegree.get(unit.id) + 1)
      dependents.get(dependency).push(unit.id)
    }
  }
  const ready = [...indegree.entries()]
    .filter(([, count]) => count === 0)
    .map(([id]) => id)
  let visited = 0
  while (ready.length) {
    const id = ready.shift()
    visited += 1
    for (const dependent of dependents.get(id) || []) {
      indegree.set(dependent, indegree.get(dependent) - 1)
      if (indegree.get(dependent) === 0) ready.push(dependent)
    }
  }
  if (visited !== plan.units.length) errors.push('unit dependency graph has a cycle')

  for (let left = 0; left < plan.units.length; left++) {
    for (let right = left + 1; right < plan.units.length; right++) {
      const a = plan.units[left]
      const b = plan.units[right]
      if (!a.writes || !b.writes) continue
      const ordered = dependencyClosure(plan.units, a.id).has(b.id)
        || dependencyClosure(plan.units, b.id).has(a.id)
      if (ordered) continue
      if (a.paths.some(x => b.paths.some(y => scopesOverlap(x, y)))) {
        errors.push(`${a.id} and ${b.id}: overlapping concurrent write scopes`)
      }
    }
  }
  if (!plan.repoClean && plan.units.some(unit => unit.writes)) {
    errors.push('main checkout is dirty; isolated writers would miss local state')
  }
  return Array.from(new Set(errors))
}

function stableBucket(value, modulus) {
  let hash = 2166136261
  for (const char of String(value)) {
    hash ^= char.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0) % modulus
}

function verificationCount(unit, cohortFirst) {
  if (unit.risk === 'critical') return 2
  if (unit.risk === 'high') return 1
  if (securityTask && unit.risk === 'medium') return 1
  if (unit.risk === 'medium') {
    return cohortFirst || stableBucket(`${workflowRunId}:${unit.id}`, 4) === 0
      ? 1
      : 0
  }
  return cohortFirst || stableBucket(`${workflowRunId}:${unit.id}`, 10) === 0
    ? 1
    : 0
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
  return Array.from(new Set([
    primary,
    ...(Array.isArray(selected.fallback_order)
      ? selected.fallback_order.map(String)
      : []),
  ])).slice(0, 4)
}

function ownerRoutes(unit, writingOrdinal) {
  const selected = routes(unit.persona)
  if (
    !unit.writes
    || !selected[0].startsWith('gpt-5.6')
    || writingOrdinal % 4 === 1
  ) {
    return selected
  }
  const opus = selected.find(model => model.startsWith('opus-5'))
    || 'opus-5-bounded'
  return [opus, ...selected.filter(model => model !== opus)]
}

phase('Plan')
const plannerModel = 'opus-5-bounded'
const plan = await agent(`READ-ONLY SWEEP PLANNER
WORKFLOW RUN: ${workflowRunId}
ROUTED MODEL: ${plannerModel}
WORKSPACE: ${workspace}

PROJECT TASK:
${task}

AUTHORIZATION AND TARGET BOUNDARY:
${authorization}

PROJECT ACCEPTANCE:
${acceptance.length
  ? acceptance.map((item, index) => `${index + 1}. ${item}`).join('\n')
  : 'No explicit project acceptance was supplied; report this as a blocker.'}

BEADS:
${tracking ? JSON.stringify(tracking).slice(0, 6000) : 'No Bead is attached.'}

Inspect the repository, current HEAD, status, project instructions, existing
work, and real test commands. Do not edit. Emit at most ${maxUnits} independently
reviewable, semantically distinct units in a dependency DAG. Deduplicate units
that would produce the same artifact or test the same claim. Set writes=true
only when the unit changes files. The paths field is exclusive write ownership,
not a list of files inspected: every writes=false unit MUST return paths=[] and
may name inspected files in its objective, criteria, and checks instead.
Every unit id MUST be lowercase and match
^[a-z0-9][a-z0-9._-]{0,63}$. Every writing path MUST be relative to the
workspace: never emit an absolute path, .git path, or parent traversal.
Writing units need disjoint concurrent path scopes and real checks. Add a
dependency whenever units overlap or consume another unit's result. Assign the
best owner persona. Do not emit persona-review units or units whose only
purpose is to rerun project-wide integration checks; the parent runs these
after merge:
${integrationChecks.length
  ? integrationChecks.join('\n')
  : 'No extra integration checks were supplied.'}
Return blocked if uncommitted state makes isolated writers unsound.`, {
  label: 'sweep-planner',
  phase: 'Plan',
  agentType: agentTypeForModel(plannerModel),
  schema: planSchema,
})

phase('Validate')
const planErrors = validatePlan(plan)
if (planErrors.length) {
  return {
    workflowRunId,
    status: 'blocked',
    stopReason: 'invalid-plan',
    task,
    workspace,
    tracking,
    routes: assignments,
    maxUnits,
    maxConcurrency,
    integrationChecks,
    plan,
    planErrors,
  }
}

const seenCohorts = new Set()
let writingOrdinal = 0
const units = plan.units.map(unit => {
  const cohort = `${unit.risk}:${unit.kind}:${unit.writes ? 'write' : 'read'}`
  const reviewCount = verificationCount(unit, !seenCohorts.has(cohort))
  seenCohorts.add(cohort)
  if (unit.writes) writingOrdinal += 1
  const owner = ownerRoutes(unit, writingOrdinal)
  return {
    ...unit,
    reviewCount,
    ownerModel: owner[0],
    ownerFallbacks: owner.slice(1),
  }
})

return {
  workflowRunId,
  status: 'planned',
  stopReason: 'planned',
  task,
  workspace,
  tracking,
  routes: assignments,
  maxUnits,
  maxConcurrency,
  integrationChecks,
  plan: {
    ...plan,
    units,
  },
  planErrors: [],
}
