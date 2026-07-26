export const meta = {
  name: 'fugu-frontier',
  description: 'Read-only best-first Bead frontier planner with bounded repository inspection and deterministic scope validation',
  phases: [
    { title: 'Inspect frontier', detail: 'compare ready work against repository evidence' },
    { title: 'Validate selection', detail: 'reject unsafe, unknown, or overlapping work' },
  ],
}

let input = {}
if (args && typeof args === 'object') {
  input = args
} else if (typeof args === 'string' && args.trim()) {
  try {
    input = JSON.parse(args)
  } catch {
    return { status: 'rejected', reason: 'fugu-frontier args must be valid JSON' }
  }
}

const task = String(input.task || '').trim()
const workspace = String(input.workspace || '').trim()
const candidates = Array.isArray(input.candidates) ? input.candidates : []
const maxSelected = Math.max(1, Math.min(Number(input.maxSelected || 2), 2))
if (!task || !workspace || !candidates.length) {
  return {
    status: 'rejected',
    reason: 'fugu-frontier requires task, workspace, and candidates',
  }
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

function parsePlannerOutput(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return { plan: value, error: '' }
  }
  const raw = String(value || '').trim()
  if (!raw) return { plan: null, error: 'planner returned empty output' }
  const fenced = raw.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i)
  try {
    const plan = JSON.parse(fenced ? fenced[1].trim() : raw)
    if (!plan || typeof plan !== 'object' || Array.isArray(plan)) {
      return { plan: null, error: 'planner output is not a JSON object' }
    }
    return { plan, error: '' }
  } catch (error) {
    return {
      plan: null,
      error: `planner output is not valid JSON: ${String(error.message || error)}`,
    }
  }
}

function validatePlan(plan, candidateIds, selectionLimit) {
  const errors = []
  if (!plan || plan.status !== 'completed') {
    return ['planner did not complete']
  }
  if (!Array.isArray(plan.selected) || !plan.selected.length) {
    return ['plan contains no selected Beads']
  }
  if (plan.selected.length > selectionLimit) {
    errors.push(`plan selected ${plan.selected.length} Beads; maximum is ${selectionLimit}`)
  }
  const selectedIds = new Set()
  const risks = new Set(['low', 'medium', 'high', 'critical'])
  const capabilities = new Set([
    'owner',
    'researcher',
    'verifier',
    'challenger',
    'specialist',
  ])
  for (const item of plan.selected) {
    const id = String(item.issueId || '')
    if (!candidateIds.has(id)) errors.push(`unknown selected Bead: ${id || '<empty>'}`)
    if (selectedIds.has(id)) errors.push(`duplicate selected Bead: ${id}`)
    selectedIds.add(id)
    if (!String(item.reason || '').trim()) errors.push(`${id}: empty selection reason`)
    if (!String(item.firstStep || '').trim()) errors.push(`${id}: empty first step`)
    if (!String(item.expectedEvidence || '').trim()) {
      errors.push(`${id}: empty expected evidence`)
    }
    if (!risks.has(item.risk)) errors.push(`${id}: invalid risk`)
    if (!capabilities.has(item.capability)) errors.push(`${id}: invalid capability`)
    if (typeof item.writes !== 'boolean') errors.push(`${id}: writes must be boolean`)
    if (!Array.isArray(item.paths) || item.paths.some(path => !safePath(path))) {
      errors.push(`${id}: unsafe or malformed path scope`)
    } else if (item.writes && !item.paths.length) {
      errors.push(`${id}: writing work requires at least one path scope`)
    } else if (!item.writes && item.paths.length) {
      errors.push(`${id}: read-only work cannot claim write paths`)
    }
  }
  for (let left = 0; left < plan.selected.length; left++) {
    for (let right = left + 1; right < plan.selected.length; right++) {
      const a = plan.selected[left]
      const b = plan.selected[right]
      if (!a.writes || !b.writes) continue
      if (a.paths.some(x => b.paths.some(y => scopesOverlap(x, y)))) {
        errors.push(`${a.issueId} and ${b.issueId}: overlapping write scopes`)
      }
    }
  }
  if (!Array.isArray(plan.dependencyHypotheses)) {
    errors.push('dependencyHypotheses must be an array')
  } else {
    for (const edge of plan.dependencyHypotheses) {
      const issueId = String(edge.issueId || '')
      const dependsOnId = String(edge.dependsOnId || '')
      if (!candidateIds.has(issueId) || !candidateIds.has(dependsOnId)) {
        errors.push(`dependency hypothesis references an unknown Bead: ${issueId} -> ${dependsOnId}`)
      }
      if (issueId === dependsOnId) errors.push(`${issueId}: self dependency hypothesis`)
      if (!String(edge.evidence || '').trim()) {
        errors.push(`${issueId} -> ${dependsOnId}: dependency evidence is empty`)
      }
    }
  }
  return Array.from(new Set(errors))
}

phase('Inspect frontier')
const rawPlan = await agent(`READ-ONLY DELIVERY FRONTIER PLANNER
WORKSPACE: ${workspace}
OPERATOR INSTRUCTION: ${task}
MAXIMUM SELECTION: ${maxSelected}

RANKED BEADS FRONTIER:
${JSON.stringify(candidates).slice(0, 30000)}

Inspect only enough repository state to choose the highest-value next delivery
move. Select one Bead by default. Select two only if their first steps and
write scopes are independent. Do not claim, update, create, or close Beads.
Personas are conditional capabilities: use owner by default; researcher only
for missing evidence; verifier for risky closure claims; challenger for
contradictory evidence or repeated failure; specialist for a concrete domain
need. Dependency observations are hypotheses only and require cited evidence.
Return exactly one JSON object with this shape and no Markdown fence:
{"status":"completed|blocked","summary":"...","selected":[{"issueId":"...","reason":"...","firstStep":"...","expectedEvidence":"...","risk":"low|medium|high|critical","capability":"owner|researcher|verifier|challenger|specialist","writes":true,"paths":["relative/path/**"]}],"dependencyHypotheses":[{"issueId":"...","dependsOnId":"...","confidence":"low|medium|high","evidence":"..."}]}`, {
  label: 'frontier-planner',
  phase: 'Inspect frontier',
  agentType: 'orchestrator:frontier-planner',
})

phase('Validate selection')
const parsed = parsePlannerOutput(rawPlan)
const plan = parsed.plan
const candidateIds = new Set(candidates.map(item => String(item.id || '')))
const planErrors = parsed.error
  ? [parsed.error]
  : validatePlan(plan, candidateIds, maxSelected)
if (planErrors.length) {
  return {
    status: 'blocked',
    stopReason: 'invalid-frontier-plan',
    task,
    workspace,
    plan,
    planErrors,
  }
}

return {
  status: 'planned',
  stopReason: 'frontier-planned',
  task,
  workspace,
  execution: plan.selected.length === 2 ? 'parallel-candidate' : 'single',
  plan,
  planErrors: [],
}
