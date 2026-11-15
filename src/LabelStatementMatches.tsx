import { useEffect, useState } from 'react'
import { fetchLabelStatementLookup } from './api'
import type { LabelStatementsLookup } from './api'

// Shown under the pair and stack checkers. It quotes FDA label text for the names that were
// typed. It never scores anything and never turns "not assessed" into an answer.

const NONE_MESSAGE =
  'No FDA label statement in this collection names these together. This does not mean the combination is safe.'

const UNCHECKED_MESSAGE =
  'FDA label statements could not be checked. Nothing has been assessed.'

type LookupState = 'idle' | 'loading' | 'done' | 'error'

function useLookup(names: string[], requestId: number, minimumNames: number) {
  // The reply is kept with the request it answers, so a reply for earlier names is never shown.
  const [reply, setReply] = useState<{
    requestId: number
    state: LookupState
    lookup: LabelStatementsLookup | null
  }>({ requestId: 0, state: 'idle', lookup: null })
  const inactive = requestId === 0 || names.length < minimumNames

  useEffect(() => {
    if (inactive) {
      return
    }

    let active = true

    fetchLabelStatementLookup(names)
      .then((response) => {
        if (active) {
          setReply({ requestId, state: 'done', lookup: response })
        }
      })
      .catch(() => {
        if (active) {
          setReply({ requestId, state: 'error', lookup: null })
        }
      })

    return () => {
      active = false
    }
    // A new requestId is the signal to look up the names captured with it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId])

  // Decided while rendering, not in an effect, so cleared names hide the block in the same
  // paint and a new check never flashes the previous answer.
  if (inactive) {
    return { state: 'idle' as LookupState, lookup: null }
  }
  if (reply.requestId !== requestId) {
    return { state: 'loading' as LookupState, lookup: null }
  }
  return { state: reply.state, lookup: reply.lookup }
}

function labelCountText(count: string): string {
  return `appears in ${count} ${Number(count) === 1 ? 'label' : 'labels'}`
}

interface MatchesProps {
  names: string[]
  requestId: number
}

export default function LabelStatementMatches({ names, requestId }: MatchesProps) {
  const { state, lookup } = useLookup(names, requestId, 2)

  if (state === 'idle') {
    return null
  }

  if (state === 'loading') {
    return <p className="status">Checking FDA label statements…</p>
  }

  if (state === 'error' || !lookup || lookup.status !== 'available') {
    return (
      <p className="status status-info" role="status">
        {UNCHECKED_MESSAGE}
      </p>
    )
  }

  const unmatched = lookup.names
    .filter((entry) => entry.supplements.length === 0 && entry.drug_total === 0)
    .map((entry) => entry.input)

  return (
    <div className="label-matches" role="region" aria-label="FDA label statements for these names">
      <h3>FDA label statements</h3>
      <p className="status status-info" role="status">
        {lookup.pairs.length > 0 ? lookup.message : lookup.message || NONE_MESSAGE}
      </p>
      {unmatched.length > 0 && (
        <p className="label-statements-source">
          Not named in the label statement collection: {unmatched.join(', ')}.
        </p>
      )}
      {lookup.pairs.length > 0 && (
        <>
          <ul className="label-statement-list">
            {lookup.pairs.map((pair) => (
              <li key={`${pair.supplement_id}|${pair.drug_id}`} className="label-statement">
                <h4 className="label-match-heading">
                  {pair.supplement_name}
                  {pair.is_group_term && <span className="badge label-group-term">group term</span>}
                  {' with '}
                  {pair.drug_names_raw}
                </h4>
                {pair.items.map((item) => (
                  <div key={item.statement_id} className="label-match-item">
                    <q>{item.sentence}</q>
                    <p className="label-statements-source">
                      {labelCountText(item.label_count)}
                      {' · '}
                      <a href={item.label_url} target="_blank" rel="noopener noreferrer">
                        View label on DailyMed
                      </a>
                    </p>
                  </div>
                ))}
              </li>
            ))}
          </ul>
          {lookup.truncated && (
            <p className="label-statements-source">
              Showing {lookup.pairs.length} of {lookup.total_pairs} matching pairs. Use the FDA label
              statements section to see the rest.
            </p>
          )}
          <p className="label-statements-source">{lookup.disclaimer}</p>
        </>
      )}
    </div>
  )
}

export interface LabelStatementsFilterRequest {
  supplement?: string
  drug?: string
}

interface NameHitsProps {
  name: string
  requestId: number
  onShow: (filter: LabelStatementsFilterRequest) => void
}

// Shown under the compound search: tells the person whether the name they searched is named
// in the label statement collection, and opens those statements.
export function LabelStatementNameHits({ name, requestId, onShow }: NameHitsProps) {
  const { state, lookup } = useLookup(name ? [name] : [], requestId, 1)

  if (state !== 'done' || !lookup || lookup.status !== 'available') {
    return null
  }

  const entry = lookup.names[0]
  if (!entry || (entry.supplements.length === 0 && entry.drug_total === 0)) {
    return (
      <p className="label-statements-source" role="status">
        “{name}” is not named in the FDA label statement collection either.
      </p>
    )
  }

  return (
    <div className="label-matches" role="region" aria-label="FDA label statements naming this search">
      <p className="label-statements-source">
        Named in FDA label statements (quoted label text, not assessed by SuppTracker):
      </p>
      <ul className="pill-grid">
        {entry.supplements.map((supplement) => (
          <li key={`s-${supplement.supplement_id}`} className="pill">
            <span className="pill-name">{supplement.supplement_name}</span>
            <span className="pill-meta">
              {supplement.is_group_term ? 'Group term' : 'Supplement'} · {supplement.statements}{' '}
              {supplement.statements === 1 ? 'statement' : 'statements'}
            </span>
            <button
              type="button"
              className="ghost"
              onClick={() => onShow({ supplement: supplement.supplement_id })}
            >
              Show statements for {supplement.supplement_name}
            </button>
          </li>
        ))}
        {entry.drugs.map((drug) => (
          <li key={`d-${drug.drug_id}`} className="pill">
            <span className="pill-name">{drug.drug_names_raw}</span>
            <span className="pill-meta">
              Drug label · {drug.statements} {drug.statements === 1 ? 'statement' : 'statements'}
            </span>
            <button type="button" className="ghost" onClick={() => onShow({ drug: drug.drug_id })}>
              Show statements for {drug.drug_id}
            </button>
          </li>
        ))}
      </ul>
      {entry.drug_total > entry.drugs.length && (
        <p className="label-statements-source">
          {entry.drug_total - entry.drugs.length} more drug labels match this name.
        </p>
      )}
    </div>
  )
}
