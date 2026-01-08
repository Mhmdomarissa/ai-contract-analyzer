# Codebase Cleanup Plan - Testing Lab Only

## Backend Files to DELETE:
- [ ] `/backend/app/api/v1/endpoints/contracts.py` - Legacy contract upload/processing
- [ ] `/backend/app/api/v1/endpoints/contracts.py.backup` - Backup file
- [ ] `/backend/app/api/v1/endpoints/bilingual.py` - Not used in Testing Lab
- [ ] `/backend/app/api/v1/endpoints/conflicts.py` - Check if duplicated by compare.py
- [ ] `/backend/app/api/v1/endpoints/versions.py` - Version management not needed
- [ ] `/backend/app/crud/` - Database CRUD operations for contracts
- [ ] `/backend/app/models/` - Database models for contracts
- [ ] `/backend/app/schemas/` - Pydantic schemas for contract upload
- [ ] `/backend/app/tasks/` - Celery tasks for document processing
- [ ] `/backend/app/services/` - Check: keep only LLM-related, delete parsers/extractors
- [ ] `/backend/alembic/` - Database migrations not needed
- [ ] `/backend/alembic.ini` - Alembic config

## Backend Files to KEEP:
- [x] `/backend/app/api/v1/endpoints/compare.py` - 1→1 comparison
- [x] `/backend/app/api/v1/endpoints/batch_compare.py` - 1→N comparison
- [x] `/backend/app/api/v1/endpoints/all_vs_all_compare.py` - N→N with self-check
- [x] `/backend/app/api/v1/endpoints/chat.py` - Chatbot
- [x] `/backend/app/core/` - Config, settings
- [x] `/backend/app/utils/` - Shared utilities
- [x] `/backend/app/main.py` - FastAPI app entry

## Frontend Files to DELETE:
- [ ] `/frontend/src/app/page.tsx.backup` - Backup file
- [ ] `/frontend/src/app/page.tsx.broken` - Broken file
- [ ] `/frontend/src/components/HierarchicalClauseViewer.tsx` - Not used in Testing Lab
- [ ] `/frontend/src/components/organisms/` - Check for unused components
- [ ] `/frontend/src/components/pages/` - Check for old pages
- [ ] `/frontend/src/features/` - Keep only comparison slices, delete contract upload

## Frontend Files to KEEP:
- [x] `/frontend/src/components/AllVsAllComparison.tsx` - N→N UI
- [x] `/frontend/src/components/BatchComparison.tsx` - 1→N UI
- [x] `/frontend/src/components/ChatPanel.tsx` - Chat UI
- [x] `/frontend/src/components/FloatingChatButton.tsx` - Chat button
- [x] `/frontend/src/features/allVsAllComparison/` - N→N Redux slice
- [x] `/frontend/src/app/page.tsx` - Main landing page
- [x] `/frontend/src/components/ui/` - UI primitives

## Steps:
1. Backup current state
2. Remove backend unused files
3. Clean up backend routes
4. Remove frontend unused files
5. Clean up frontend routes
6. Update dependencies
7. Test build
8. Commit
