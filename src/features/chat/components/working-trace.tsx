"use client";

import { useState } from "react";
import { ChatTrace, ChatTraceSource } from "@/types";

interface WorkingTraceProps {
  trace: ChatTrace | null;
  isStreaming?: boolean;
}

const formatScore = (score: number) => score.toFixed(2);

const sourceLabel = (source: ChatTraceSource) => {
  const party = source.partyAbbreviation ? `${source.partyAbbreviation} · ` : "";
  const page = source.page ? ` · sida ${source.page}` : "";
  return `${party}${source.documentPath}${page}`;
};

const modeLabel = (mode: ChatTrace["mode"]) => mode === "multi-step" ? "Flersteg" : "Ensteg";

export default function WorkingTrace({ trace, isStreaming = false }: WorkingTraceProps) {
  const [expanded, setExpanded] = useState(false);

  if (!trace) {
    return (
      <div className="mb-3 text-sm text-gray-500">
        Arbetslogg
      </div>
    );
  }

  const isComplete = trace.status === "complete";
  const showFullTrace = isStreaming || expanded;
  const queryCount = trace.queries.length;
  const activityEvents = isComplete ? trace.events : trace.events.slice(-8);

  return (
    <div className="mb-4 border-b border-gray-200 pb-3 text-sm text-gray-700">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium text-gray-900">
          Arbetslogg
          {isComplete && (
            <span className="ml-2 font-normal text-gray-500">
              {queryCount} sökningar · {trace.segmentCount} källsegment · {trace.documentCount} dokument
            </span>
          )}
        </div>

        {isComplete && !isStreaming && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="text-sm font-medium text-blue-600 hover:text-blue-800"
          >
            {expanded ? "Dölj logg" : "Visa logg"}
          </button>
        )}
      </div>

      {showFullTrace ? (
        <div className="mt-3 space-y-4">
          <div>
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">
              Aktivitet
            </div>
            <div className="max-h-32 space-y-1 overflow-y-auto pr-2">
              {activityEvents.map((event, index) => (
                <div key={`${event}-${index}`} className="leading-relaxed">
                  {event}
                </div>
              ))}
              {trace.status === "running" && (
                <div className="leading-relaxed text-blue-700">
                  Arbetar...
                </div>
              )}
            </div>
          </div>

          {isComplete && (
            <>
              <div>
                <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">
                  Källhämtning
                </div>
                <div className="space-y-1">
                  <div>Läge: {modeLabel(trace.mode)}</div>
                  <div>Sökningar: {queryCount}</div>
                  <div>Källsegment använda: {trace.segmentCount}</div>
                  <div>Dokument använda: {trace.documentCount}</div>
                  {trace.topicName && <div>Ämne: {trace.topicName}</div>}
                </div>
              </div>

              {trace.queries.length > 0 && (
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                    Sökningar
                  </div>
                  <div className="space-y-3">
                    {trace.queries.map((query, index) => (
                      <div key={`${query.query}-${index}`}>
                        <div className="font-medium text-gray-900">
                          {index + 1}. {query.query}
                          {query.partyFilter && (
                            <span className="ml-2 font-normal text-gray-500">
                              Parti: {query.partyFilter}
                            </span>
                          )}
                        </div>
                        <div className="text-gray-600">
                          {query.error
                            ? `Misslyckades: ${query.error}`
                            : `Hämtade ${query.returnedSegments ?? 0} segment`}
                        </div>
                        {query.sources && query.sources.length > 0 && (
                          <div className="mt-2 max-h-48 space-y-2 overflow-y-auto border-l border-gray-200 pl-3">
                            {query.sources.map((source, sourceIndex) => (
                              <div key={`${source.documentPath}-${sourceIndex}`}>
                                <div className="text-gray-800">
                                  {sourceIndex + 1}. {sourceLabel(source)}
                                </div>
                                <div className="text-gray-600">
                                  Träffpoäng: {formatScore(source.similarityScore)}
                                </div>
                                {source.publicUrl && (
                                  <a
                                    href={source.publicUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="break-all text-blue-600 hover:text-blue-800 underline"
                                  >
                                    {source.publicUrl}
                                  </a>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {trace.sources.length > 0 && (
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                    Källor som visades för modellen
                  </div>
                  <div className="max-h-80 space-y-4 overflow-y-auto pr-2">
                    {trace.sources.map((source, index) => (
                      <div key={`${source.documentPath}-${index}`}>
                        <div className="font-medium text-gray-900">
                          {index + 1}. {sourceLabel(source)}
                        </div>
                        <div className="text-gray-600">Träffpoäng: {formatScore(source.similarityScore)}</div>
                        {source.publicUrl && (
                          <a
                            href={source.publicUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="break-all text-blue-600 hover:text-blue-800 underline"
                          >
                            {source.publicUrl}
                          </a>
                        )}
                        <div className="mt-1 text-gray-700">
                          Utdrag: &quot;{source.snippet}&quot;
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
