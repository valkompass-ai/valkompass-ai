"use client";

import ReactMarkdown from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { deepmerge } from 'deepmerge-ts';
import { StreamingChatState } from '../hooks/use-chat';
import WorkingTrace from './working-trace';

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

  const answer = stream?.answer ?? '';

  return (
    <div className="flex px-2 py-2 sm:p-4 justify-start">
      <div className="prose prose-sm sm:prose prose-p:my-2 rounded-xl bg-white/80 border border-gray-200 p-4 max-w-[95%] sm:w-full text-gray-800 shadow-sm">
        <WorkingTrace trace={stream?.trace ?? null} isStreaming />

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
        ) : (
          <div className="text-sm text-gray-500">Startar...</div>
        )}
      </div>
    </div>
  );
}
