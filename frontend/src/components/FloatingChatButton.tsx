/**
 * Floating Chat Button Component
 * 
 * A circular button that opens a chat panel for direct interaction with Qwen2.
 */

'use client'

import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '@/lib/store';
import { toggleChat } from '@/features/chat/chatSlice';
import { Button } from '@/components/ui/button';
import { MessageCircle, X } from 'lucide-react';
import ChatPanel from './ChatPanel';

export default function FloatingChatButton() {
  const dispatch = useDispatch<AppDispatch>();
  const { isOpen } = useSelector((state: RootState) => state.chat);

  return (
    <>
      {/* Floating Button */}
      <Button
        onClick={() => dispatch(toggleChat())}
        className="fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg z-50 hover:scale-110 transition-transform"
        size="icon"
      >
        {isOpen ? (
          <X className="h-6 w-6" />
        ) : (
          <MessageCircle className="h-6 w-6" />
        )}
      </Button>

      {/* Chat Panel */}
      {isOpen && <ChatPanel />}
    </>
  );
}
