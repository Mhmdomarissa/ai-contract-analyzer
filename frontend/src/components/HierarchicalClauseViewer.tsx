/**
 * Hierarchical Clause Viewer Component
 * 
 * Displays contract clauses in a collapsible tree structure with:
 * - Multi-level hierarchy visualization
 * - Quality scores from LLM validation
 * - Cross-reference linking
 * - Table detection indicators
 * - Search and filter capabilities
 */

import React, { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, Table, Link, AlertTriangle, CheckCircle } from 'lucide-react';

interface ClauseValidation {
  is_valid: boolean;
  confidence_score: number;
  quality_score: number;
  issues: string[];
  suggestions: string[];
  is_toc_entry: boolean;
  boundary_correct: boolean;
}

interface ClauseMetadata {
  type?: string;
  parent_clause?: string;
  has_table?: boolean;
  cross_references?: string[];
}

interface Clause {
  id: string;
  clause_number: string;
  category: string;
  text: string;
  start_char: number;
  end_char: number;
  metadata?: ClauseMetadata;
  validation?: ClauseValidation;
}

interface ClauseNode extends Clause {
  children: ClauseNode[];
  level: number;
}

interface HierarchicalClauseViewerProps {
  clauses: Clause[];
  onClauseClick?: (clause: Clause) => void;
}

const HierarchicalClauseViewer: React.FC<HierarchicalClauseViewerProps> = ({
  clauses,
  onClauseClick
}) => {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [filterByQuality, setFilterByQuality] = useState<number | null>(null);

  // Build hierarchical tree from flat clause list
  const clauseTree = useMemo(() => {
    const tree: ClauseNode[] = [];
    const nodeMap = new Map<string, ClauseNode>();

    // Sort clauses by clause number
    const sortedClauses = [...clauses].sort((a, b) => {
      const numA = parseClauseNumber(a.clause_number);
      const numB = parseClauseNumber(b.clause_number);
      return numA - numB;
    });

    sortedClauses.forEach(clause => {
      const node: ClauseNode = {
        ...clause,
        children: [],
        level: getClauseLevel(clause.clause_number)
      };

      nodeMap.set(clause.clause_number, node);

      // Determine parent
      const parent_number = clause.metadata?.parent_clause || getParentNumber(clause.clause_number);
      
      if (parent_number && nodeMap.has(parent_number)) {
        nodeMap.get(parent_number)!.children.push(node);
      } else {
        tree.push(node);
      }
    });

    return tree;
  }, [clauses]);

  // Filter clauses based on search and quality
  const filteredTree = useMemo(() => {
    if (!searchTerm && filterByQuality === null) return clauseTree;

    const filterNode = (node: ClauseNode): ClauseNode | null => {
      const matchesSearch = !searchTerm || 
        node.text.toLowerCase().includes(searchTerm.toLowerCase()) ||
        node.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
        node.clause_number.includes(searchTerm);

      const matchesQuality = filterByQuality === null ||
        (node.validation?.quality_score ?? 0) >= filterByQuality;

      const filteredChildren = node.children
        .map(filterNode)
        .filter((n): n is ClauseNode => n !== null);

      if (matchesSearch && matchesQuality) {
        return { ...node, children: filteredChildren };
      } else if (filteredChildren.length > 0) {
        return { ...node, children: filteredChildren };
      }

      return null;
    };

    return clauseTree
      .map(filterNode)
      .filter((n): n is ClauseNode => n !== null);
  }, [clauseTree, searchTerm, filterByQuality]);

  const toggleNode = (clauseNumber: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(clauseNumber)) {
        next.delete(clauseNumber);
      } else {
        next.add(clauseNumber);
      }
      return next;
    });
  };

  const expandAll = () => {
    const allNumbers = new Set<string>();
    const collectNumbers = (nodes: ClauseNode[]) => {
      nodes.forEach(node => {
        allNumbers.add(node.clause_number);
        collectNumbers(node.children);
      });
    };
    collectNumbers(clauseTree);
    setExpandedNodes(allNumbers);
  };

  const collapseAll = () => {
    setExpandedNodes(new Set());
  };

  return (
    <div className="hierarchical-clause-viewer">
      {/* Controls */}
      <div className="controls-bar mb-4 space-y-3">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Search clauses..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            onClick={expandAll}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
          >
            Expand All
          </button>
          <button
            onClick={collapseAll}
            className="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600"
          >
            Collapse All
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Min Quality:</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={filterByQuality ?? 0}
            onChange={(e) => setFilterByQuality(parseFloat(e.target.value))}
            className="flex-1"
          />
          <span className="text-sm font-medium">{(filterByQuality ?? 0).toFixed(1)}</span>
          <button
            onClick={() => setFilterByQuality(null)}
            className="text-sm text-blue-500 hover:text-blue-700"
          >
            Clear
          </button>
        </div>

        <div className="flex items-center gap-4 text-sm text-gray-600">
          <span>Total: {clauses.length} clauses</span>
          <span>Displayed: {countNodes(filteredTree)} clauses</span>
        </div>
      </div>

      {/* Clause Tree */}
      <div className="clause-tree space-y-1">
        {filteredTree.map(node => (
          <ClauseTreeNode
            key={node.id}
            node={node}
            expanded={expandedNodes.has(node.clause_number)}
            onToggle={() => toggleNode(node.clause_number)}
            onClick={() => onClauseClick?.(node)}
            level={0}
          />
        ))}
      </div>
    </div>
  );
};

interface ClauseTreeNodeProps {
  node: ClauseNode;
  expanded: boolean;
  onToggle: () => void;
  onClick: () => void;
  level: number;
}

const ClauseTreeNode: React.FC<ClauseTreeNodeProps> = ({
  node,
  expanded,
  onToggle,
  onClick,
  level
}) => {
  const hasChildren = node.children.length > 0;
  const validation = node.validation;
  const metadata = node.metadata;

  const qualityColor = validation
    ? validation.quality_score >= 0.8
      ? 'text-green-600'
      : validation.quality_score >= 0.5
      ? 'text-yellow-600'
      : 'text-red-600'
    : 'text-gray-400';

  return (
    <div className="clause-node">
      <div
        className={`clause-header flex items-start gap-2 p-3 rounded-lg hover:bg-gray-50 cursor-pointer border-l-4 ${
          validation?.is_valid === false
            ? 'border-red-500 bg-red-50'
            : validation?.quality_score && validation.quality_score >= 0.8
            ? 'border-green-500'
            : 'border-gray-300'
        }`}
        style={{ marginLeft: `${level * 24}px` }}
      >
        {/* Expand/Collapse Icon */}
        {hasChildren ? (
          <button onClick={onToggle} className="flex-shrink-0 mt-1">
            {expanded ? (
              <ChevronDown className="w-5 h-5 text-gray-600" />
            ) : (
              <ChevronRight className="w-5 h-5 text-gray-600" />
            )}
          </button>
        ) : (
          <div className="w-5 h-5" />
        )}

        {/* Clause Content */}
        <div className="flex-1 min-w-0" onClick={onClick}>
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-sm font-semibold text-blue-600">
              {node.clause_number}
            </span>
            <span className="font-medium text-gray-900">{node.category}</span>

            {/* Indicators */}
            <div className="flex gap-1 ml-auto">
              {metadata?.has_table && (
                <span className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded">
                  <Table className="w-3 h-3" />
                  Table
                </span>
              )}
              {metadata?.cross_references && metadata.cross_references.length > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded">
                  <Link className="w-3 h-3" />
                  {metadata.cross_references.length}
                </span>
              )}
              {validation && (
                <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs ${
                  validation.is_valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                } rounded`}>
                  {validation.is_valid ? (
                    <CheckCircle className="w-3 h-3" />
                  ) : (
                    <AlertTriangle className="w-3 h-3" />
                  )}
                  {(validation.quality_score * 100).toFixed(0)}%
                </span>
              )}
            </div>
          </div>

          {/* Clause Text Preview */}
          <p className="text-sm text-gray-600 line-clamp-2">
            {node.text.substring(0, 200)}
            {node.text.length > 200 && '...'}
          </p>

          {/* Validation Issues */}
          {validation && validation.issues.length > 0 && (
            <div className="mt-2 space-y-1">
              {validation.issues.map((issue, idx) => (
                <div key={idx} className="flex items-start gap-2 text-xs text-orange-600">
                  <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <span>{issue}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Children */}
      {hasChildren && expanded && (
        <div className="clause-children mt-1">
          {node.children.map(child => (
            <ClauseTreeNode
              key={child.id}
              node={child}
              expanded={false}
              onToggle={() => {}}
              onClick={() => {}}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// Helper functions
function parseClauseNumber(clauseNum: string): number {
  // Extract numeric parts for sorting
  const match = clauseNum.match(/(\d+(?:\.\d+)*)/);
  if (match) {
    const parts = match[1].split('.').map(Number);
    // Create sortable number: 1.2.3 -> 1.002003
    return parts.reduce((acc, part, idx) => acc + part * Math.pow(1000, -(idx)), 0);
  }
  return 0;
}

function getClauseLevel(clauseNum: string): number {
  const match = clauseNum.match(/(\d+(?:\.\d+)*)/);
  if (match) {
    return match[1].split('.').length;
  }
  return 0;
}

function getParentNumber(clauseNum: string): string | null {
  const match = clauseNum.match(/^(\d+(?:\.\d+)*)/);
  if (match) {
    const parts = match[1].split('.');
    if (parts.length > 1) {
      parts.pop();
      return parts.join('.');
    }
  }
  return null;
}

function countNodes(nodes: ClauseNode[]): number {
  return nodes.reduce((count, node) => count + 1 + countNodes(node.children), 0);
}

export default HierarchicalClauseViewer;
