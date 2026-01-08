#!/bin/bash
# Codebase Cleanup Script - Testing Lab Only
# Removes all unused legacy contract processing code

set -e  # Exit on error

REPO_ROOT="/home/ec2-user/apps/ai-contract-analyzer"
cd "$REPO_ROOT"

echo "================================"
echo "TESTING LAB CLEANUP - Phase 1: Backend"
echo "================================"
echo ""

# Backend cleanup
echo "🗑️  Removing unused backend endpoints..."
rm -f backend/app/api/v1/endpoints/contracts.py
rm -f backend/app/api/v1/endpoints/contracts.py.backup
rm -f backend/app/api/v1/endpoints/bilingual.py
rm -f backend/app/api/v1/endpoints/conflicts.py
rm -f backend/app/api/v1/endpoints/versions.py

echo "🗑️  Removing database-related code (CRUD, models, schemas)..."
rm -rf backend/app/crud/
rm -rf backend/app/models/
rm -rf backend/app/schemas/

echo "🗑️  Removing document processing services..."
rm -rf backend/app/services/parsers/
rm -f backend/app/services/document_parser.py
rm -f backend/app/services/ocr_service.py
rm -f backend/app/services/contracts.py
rm -f backend/app/services/clause_validator.py
rm -f backend/app/services/table_extractor.py
rm -f backend/app/services/improved_clause_extractor.py
rm -f backend/app/services/hierarchical_clause_extractor.py
rm -f backend/app/services/clause_classifier.py

echo "🗑️  Removing Celery tasks..."
rm -rf backend/app/tasks/

echo "🗑️  Removing database migrations..."
rm -rf backend/alembic/
rm -f backend/alembic.ini

echo "🗑️  Removing database module..."
rm -rf backend/app/db/

echo ""
echo "================================"
echo "TESTING LAB CLEANUP - Phase 2: Frontend"
echo "================================"
echo ""

echo "🗑️  Removing backup/broken files..."
rm -f frontend/src/app/page.tsx.backup
rm -f frontend/src/app/page.tsx.broken

echo "🗑️  Removing unused components..."
rm -f frontend/src/components/HierarchicalClauseViewer.tsx

echo "🗑️  Removing legacy contract features..."
rm -rf frontend/src/features/contract/
rm -rf frontend/src/features/contracts/

echo "🗑️  Checking organisms and pages folders..."
if [ -d "frontend/src/components/organisms" ]; then
    echo "   ℹ️  Keeping organisms/ (will check contents manually)"
fi

if [ -d "frontend/src/components/pages" ]; then
    echo "   ℹ️  Keeping pages/ (will check contents manually)"
fi

echo ""
echo "================================"
echo "✅ CLEANUP COMPLETE"
echo "================================"
echo ""
echo "Remaining backend endpoints:"
ls -1 backend/app/api/v1/endpoints/*.py 2>/dev/null || echo "  (none)"
echo ""
echo "Remaining frontend features:"
ls -1 frontend/src/features/ 2>/dev/null || echo "  (none)"
echo ""
echo "Next steps:"
echo "1. Update backend/app/api/v1/api.py"
echo "2. Update frontend routing"
echo "3. Clean pyproject.toml dependencies"
echo "4. Test build"
