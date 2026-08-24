import { useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { fetchMitreTechnique } from '../services/api';
import type { MitreTechnique } from '../types';
import {
  Badge,
  EmptyState,
  ErrorNote,
  KeyValues,
  LoadingRow,
  PageHeader,
  QuickPicks,
  SearchBar,
  Section,
} from './ui';
import {
  NA,
  fmtInt,
  fmtText,
} from '../lib/format';

const EXAMPLE_TECHNIQUES = ['T1190', 'T1059', 'T1003', 'T1566', 'T1055', 'T1053', 'T1110', 'T1021'];

export function MitreAttackView() {
  const [techniqueId, setTechniqueId] = useState('T1190');
  const [technique, setTechnique] = useState<MitreTechnique | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async (targetId?: string) => {
    const id = (targetId ?? techniqueId).trim().toUpperCase();
    if (!id) return;

    setTechniqueId(id);
    setLoading(true);
    setError(null);

    try {
      setTechnique(await fetchMitreTechnique(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Technique ${id} not found`);
      setTechnique(null);
    } finally {
      setLoading(false);
    }
  };

  // Load the default technique from the API rather than seeding the view with
  // a hardcoded copy of the ATT&CK record.
  useEffect(() => {
    runSearch('T1190');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="view-stack">
      <PageHeader
        title="MITRE ATT&CK"
        description="Technique records from the ingested MITRE ATT&CK Enterprise dataset, retrieved by technique identifier."
      />

      <Section title="Technique lookup">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <SearchBar
            id="technique-search"
            label="Technique identifier"
            placeholder="T1190 or T1003.001"
            value={techniqueId}
            onChange={setTechniqueId}
            onSubmit={() => runSearch()}
            busy={loading}
            mono
          />
          <QuickPicks label="Examples" items={EXAMPLE_TECHNIQUES} onPick={(id) => runSearch(id)} />
          <p className="meta">
            The API resolves one technique at a time (GET /api/mitre/{'{id}'}); it exposes no endpoint for listing or
            filtering the full technique catalogue.
          </p>
        </div>
      </Section>

      {error && <ErrorNote message={error} />}

      {loading && (
        <div className="card">
          <LoadingRow message="Loading technique…" />
        </div>
      )}

      {!loading && !technique && !error && (
        <div className="card">
          <EmptyState title="No technique loaded" message="Enter a MITRE ATT&CK technique identifier above." />
        </div>
      )}

      {technique && !loading && (
        <>
          <Section
            title={`${technique.technique_id} — ${fmtText(technique.name)}`}
            description={technique.tactics?.length ? `Tactics: ${technique.tactics.join(', ')}` : 'No tactic recorded'}
            actions={
              technique.url ? (
                <a className="btn btn-sm" href={technique.url} target="_blank" rel="noreferrer">
                  ATT&CK reference
                  <ExternalLink size={13} aria-hidden="true" />
                </a>
              ) : undefined
            }
          >
            <p style={{ fontSize: '0.8125rem', lineHeight: 1.6 }}>{fmtText(technique.description)}</p>
          </Section>

          <div className="two-col">
            <Section title="Classification">
              <KeyValues
                rows={[
                  { key: 'Technique ID', value: technique.technique_id, mono: true },
                  { key: 'Tactics', value: technique.tactics?.length ? technique.tactics.join(', ') : NA },
                  { key: 'Platforms', value: technique.platforms?.length ? technique.platforms.join(', ') : NA },
                  { key: 'Sub-techniques', value: fmtInt(technique.sub_techniques?.length ?? 0), mono: true },
                  { key: 'Mitigations', value: fmtInt(technique.mitigations?.length ?? 0), mono: true },
                ]}
              />
            </Section>

            <Section title="Sub-techniques">
              {technique.sub_techniques?.length ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {technique.sub_techniques.map((sub) => (
                    <button key={sub} type="button" className="btn btn-sm mono" onClick={() => runSearch(sub)}>
                      {sub}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="meta">{NA} — the record lists no sub-techniques.</p>
              )}
            </Section>
          </div>

          <Section title="Mitigations" description="Countermeasures recorded against this technique." flush>
            {technique.mitigations?.length ? (
              <div className="table-scroll">
                <table className="table">
                  <caption className="sr-only">Mitigations mapped to this technique</caption>
                  <thead>
                    <tr>
                      <th scope="col" style={{ width: 120 }}>Mitigation ID</th>
                      <th scope="col">Name</th>
                    </tr>
                  </thead>
                  <tbody>
                    {technique.mitigations.map((mitigation) => (
                      <tr key={mitigation.mitigation_id}>
                        <td className="mono">{mitigation.mitigation_id}</td>
                        <td>{fmtText(mitigation.name)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No mitigations recorded" message="The ingested record lists no mitigations for this technique." />
            )}
          </Section>

          <Section title="Platforms">
            {technique.platforms?.length ? (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {technique.platforms.map((platform) => (
                  <Badge key={platform} tone="neutral">
                    {platform}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="meta">{NA} — no platforms recorded.</p>
            )}
          </Section>
        </>
      )}
    </div>
  );
}
