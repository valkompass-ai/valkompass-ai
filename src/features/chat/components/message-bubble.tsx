import ReactMarkdown from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { deepmerge } from 'deepmerge-ts';
import { ChatTrace } from '@/types';
import WorkingTrace from './working-trace';

interface MessageBubbleProps {
  message: string;
  role: "user" | "ai";
  trace?: ChatTrace;
}

export default function MessageBubble({ message, role, trace }: MessageBubbleProps) {
  const isUser = role === "user";

  const customSchema = deepmerge(defaultSchema, {
    attributes: {
      ...defaultSchema.attributes,
      // Allow class attribute for syntax highlighting if you use rehype-prism or similar
      // e.g. code: [...(defaultSchema.attributes?.code || []), 'className'],
      // Allow id attribute for headers if needed for linking
      '*': [...(defaultSchema.attributes?.['*'] || []), 'id'],
    },
    // Add any tags you want to allow that might be stripped by default
    // For example, if you want to allow iframes (though be careful with these)
    // tagNames: [...(defaultSchema.tagNames || []), 'iframe'],
  });

  return (
    <div className={`flex px-2 py-2 sm:p-4 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`prose prose-sm sm:prose prose-p:my-2 sm:prose-p:m-0 rounded-xl whitespace-pre-line break-words ${
          isUser 
            ? "bg-indigo-500 max-w-[85%] sm:max-w-xs text-white px-4 py-3 sm:p-3" 
            : "bg-white/80 border border-gray-200 p-4 max-w-[95%] sm:w-full text-gray-800 shadow-sm"
        }`}
      >
        {isUser ? (
          <span className="text-sm sm:text-base leading-relaxed">{message}</span>
        ) : (
          <>
            {trace && <WorkingTrace trace={trace} />}
            <ReactMarkdown
              rehypePlugins={[[rehypeSanitize, customSchema]]}
              components={{
                a: ({ ...props}) => (
                  <a className="text-blue-600 hover:text-blue-800 underline touch-manipulation" target="_blank" rel="noopener noreferrer" {...props} />
                ),
                p: ({ ...props }) => (
                  <p className="text-sm sm:text-base leading-relaxed mb-3 last:mb-0" {...props} />
                ),
                h1: ({ ...props }) => (
                  <h1 className="text-lg sm:text-xl font-bold mb-3 mt-2" {...props} />
                ),
                h2: ({ ...props }) => (
                  <h2 className="text-base sm:text-lg font-semibold mb-2 mt-2" {...props} />
                ),
                h3: ({ ...props }) => (
                  <h3 className="text-sm sm:text-base font-semibold mb-2 mt-2" {...props} />
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
              {message}
            </ReactMarkdown>
          </>
        )}
      </div>
    </div>
  );
}
