"use client";

import ReactMarkdown from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { deepmerge } from 'deepmerge-ts';
import { StreamingChatState } from '../hooks/use-chat';

interface MessageBubbleLoadingProps {
  stream?: StreamingChatState | null;
}

export default function MessageBubbleLoading({ stream }: MessageBubbleLoadingProps) {
  const customSchema = deepmerge(defaultSchema, {
    attributes: {
      ...defaultSchema.attributes,
      '*': [...(defaultSchema.attributes?.['*'] || []), 'id'],
    },
  });

  const reasoning = stream?.reasoning.trim() ?? '';
  const answer = stream?.answer ?? '';
  const isReasoningCollapsed = Boolean(stream?.reasoningCollapsed && reasoning);

  return (
    <div className="flex px-2 py-2 sm:p-4 justify-start">
      <div className="prose prose-sm sm:prose prose-p:my-2 rounded-xl bg-white/80 border border-gray-200 p-4 max-w-[95%] sm:w-full text-gray-800 shadow-sm">
        {reasoning && (
          isReasoningCollapsed ? (
            <details className="mb-3 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600">
              <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-gray-500">
                Visa resonemang
              </summary>
              <div className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                {reasoning}
              </div>
            </details>
          ) : (
            <div className="mb-3 rounded-md border border-blue-100 bg-blue-50 px-3 py-2">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-blue-700">
                Resonemang
              </div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
                {reasoning}
                <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-blue-500 align-text-bottom" />
              </div>
            </div>
          )
        )}

        {answer ? (
          <ReactMarkdown
            rehypePlugins={[[rehypeSanitize, customSchema]]}
            components={{
              a: ({ ...props}) => (
                <a className="text-blue-600 hover:text-blue-800 underline touch-manipulation" target="_blank" rel="noopener noreferrer" {...props} />
              ),
              p: ({ ...props }) => (
                <p className="text-sm sm:text-base leading-relaxed mb-3 last:mb-0" {...props} />
              ),
              ul: ({ ...props }) => (
                <ul className="list-disc list-inside space-y-1 mb-3" {...props} />
              ),
              ol: ({ ...props }) => (
                <ol className="list-decimal list-inside space-y-1 mb-3" {...props} />
              ),
              li: ({ ...props }) => (
                <li className="text-sm sm:text-base leading-relaxed" {...props} />
              ),
            }}
          >
            {answer}
          </ReactMarkdown>
        ) : !reasoning ? (
          <div className="text-sm text-gray-500">Startar...</div>
        ) : null}
      </div>
    </div>
  );
}
