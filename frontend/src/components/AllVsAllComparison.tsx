/**
 * All-vs-All Comparison Component
 * 
 * Compare all clauses against each other (N → N).
 * Generates N*(N-1)/2 unique pair comparisons.
 * Results are streamed and displayed in real-time.
 */

'use client'

import { useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '@/lib/store';
import {
  addClause,
  removeClause,
  updateClause,
  setClauses,
  setPairPrompt,
  setSelfPrompt,
  resetPairPrompt,
  resetSelfPrompt,
  startComparison,
  addResult,
  completeComparison,
  cancelComparison,
  setError,
  clearAll,
} from '@/features/allVsAllComparison/allVsAllComparisonSlice';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { 
  Network, 
  RotateCcw, 
  Trash2, 
  AlertTriangle, 
  CheckCircle,
  Clock,
  Zap,
  Plus,
  X,
  ArrowLeftRight
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';

export default function AllVsAllComparisonPage() {
  const dispatch = useDispatch<AppDispatch>();
  const {
    clauses,
    pairPrompt,
    selfPrompt,
    results,
    isComparing,
    totalComparisons,
    completedCount,
    error,
  } = useSelector((state: RootState) => state.allVsAllComparison);
  
  const { toast } = useToast();
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Initialize with 2 empty clauses
  useEffect(() => {
    if (clauses.length === 0) {
      dispatch(addClause(''));
      dispatch(addClause(''));
    }
  }, [dispatch, clauses.length]);

  const handleAddClause = () => {
    if (clauses.length >= 50) {
      toast({
        title: "Maximum Reached",
        description: "You can compare up to 50 clauses at once.",
        variant: "destructive",
      });
      return;
    }
    dispatch(addClause(''));
  };

  const handleRemoveClause = (index: number) => {
    if (clauses.length <= 2) {
      toast({
        title: "Cannot Remove",
        description: "At least 2 clauses are required for comparison.",
        variant: "destructive",
      });
      return;
    }
    dispatch(removeClause(index));
  };

  const handleUpdateClause = (index: number, value: string) => {
    dispatch(updateClause({ index, value }));
  };

  const handleStartComparison = async () => {
    // Filter out empty clauses
    const validClauses = clauses.filter(c => c.trim().length > 0);

    if (validClauses.length < 2) {
      toast({
        title: "Insufficient Clauses",
        description: "Please provide at least 2 clauses for comparison.",
        variant: "destructive",
      });
      return;
    }

    const n = validClauses.length;
    // Total: n self-checks + n*(n-1)/2 pair-checks = n*(n+1)/2
    const totalPairs = (n * (n + 1)) / 2;

    dispatch(setClauses(validClauses));
    dispatch(startComparison({ totalComparisons: totalPairs, clauseCount: n }));

    // Create abort controller for cancellation
    abortControllerRef.current = new AbortController();

    // Start SSE connection
    try {
      const response = await fetch('/api/v1/compare/all-vs-all', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          clauses: validClauses,
          pair_prompt: pairPrompt,
          self_prompt: selfPrompt,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = ''; // Buffer for incomplete chunks
      let processedCount = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log(`SSE stream ended. Processed ${processedCount} events.`);
          break;
        }

        // Decode and add to buffer
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        // Keep the last incomplete line in the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const jsonStr = line.slice(6).trim();
              if (!jsonStr) continue;
              
              const data = JSON.parse(jsonStr);
              processedCount++;

              if (data.type === 'result') {
                dispatch(addResult(data.data));
                console.log(`Result ${processedCount}: Clause ${data.data.clause_i_index + 1} vs ${data.data.clause_j_index + 1}, Conflict: ${data.data.conflict}`);
              } else if (data.type === 'complete') {
                dispatch(completeComparison());
                console.log(`Comparison completed. Total events: ${processedCount}`);
                toast({
                  title: "Comparison Complete",
                  description: `All ${totalPairs} comparisons finished successfully.`,
                });
              } else if (data.type === 'error') {
                dispatch(setError(data.message));
                console.error(`Error event received: ${data.message}`);
                toast({
                  title: "Error",
                  description: data.message,
                  variant: "destructive",
                });
              } else if (data.type === 'status') {
                console.log(`Status: ${data.message}`);
              }
            } catch (parseErr) {
              console.error(`Failed to parse SSE line: "${line}"`, parseErr);
              // Continue processing other lines instead of breaking
            }
          }
        }
      }
    } catch (err) {
      // Check if it was a user cancellation
      if (err instanceof Error && err.name === 'AbortError') {
        console.log('Comparison cancelled by user');
        toast({
          title: "Comparison Cancelled",
          description: "The comparison was stopped.",
        });
      } else {
        const message = err instanceof Error ? err.message : 'Failed to compare clauses';
        dispatch(setError(message));
        toast({
          title: "Comparison Failed",
          description: message,
          variant: "destructive",
        });
      }
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleStopComparison = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      dispatch(cancelComparison());
      toast({
        title: "Stopping Comparison",
        description: "The comparison is being stopped...",
      });
    }
  };

  const handleClearAll = () => {
    dispatch(clearAll());
    // Add back 2 empty clauses
    dispatch(addClause(''));
    dispatch(addClause(''));
    toast({
      title: "Cleared",
      description: "All inputs and results have been cleared.",
    });
  };

  const progress = totalComparisons > 0 ? (completedCount / totalComparisons) * 100 : 0;

  const conflictCount = results.filter(r => r.conflict).length;

  return (
    <div className="container mx-auto py-10 space-y-8 max-w-7xl">
      <div className="space-y-2">
        <h1 className="text-4xl font-bold flex items-center gap-3">
          <Network className="w-10 h-10 text-primary" />
          All-vs-All Comparison (N → N)
        </h1>
        <p className="text-muted-foreground">
          Compare every clause against every other clause AND check each clause for self-consistency. For {clauses.filter(c => c.trim()).length} clauses, this generates{' '}
          <span className="font-semibold">
            {clauses.filter(c => c.trim()).length} self-checks + {(clauses.filter(c => c.trim()).length * (clauses.filter(c => c.trim()).length - 1)) / 2} pair comparisons = {(clauses.filter(c => c.trim()).length * (clauses.filter(c => c.trim()).length + 1)) / 2} total
          </span>
        </p>
      </div>

      {/* Input Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg">Clauses to Compare</CardTitle>
              <CardDescription>Each clause will be compared with all other clauses</CardDescription>
            </div>
            <Button
              onClick={handleAddClause}
              disabled={isComparing || clauses.length >= 50}
              size="sm"
              variant="outline"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Clause
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {clauses.map((clause, index) => (
            <div key={index} className="space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground min-w-[120px]">
                  <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-semibold">
                    {index + 1}
                  </div>
                  <ArrowLeftRight className="w-4 h-4" />
                  <span className="font-medium">All others</span>
                </div>
                <div className="flex-1">
                  <Textarea
                    value={clause}
                    onChange={(e) => handleUpdateClause(index, e.target.value)}
                    placeholder={`Enter clause ${index + 1}...`}
                    className="min-h-[100px] font-mono text-sm"
                    disabled={isComparing}
                  />
                </div>
                <Button
                  onClick={() => handleRemoveClause(index)}
                  disabled={isComparing || clauses.length <= 2}
                  size="icon"
                  variant="ghost"
                  className="shrink-0"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <div className="text-xs text-muted-foreground ml-[135px]">
                {clause.length} characters
              </div>
            </div>
          ))}
          
          <div className="pt-2 border-t">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                Total clauses: <span className="font-semibold">{clauses.filter(c => c.trim()).length}</span>
              </span>
              <span className="text-muted-foreground">
                Total comparisons: <span className="font-semibold">
                  {clauses.filter(c => c.trim()).length} self + {(clauses.filter(c => c.trim()).length * (clauses.filter(c => c.trim()).length - 1)) / 2} pair = {(clauses.filter(c => c.trim()).length * (clauses.filter(c => c.trim()).length + 1)) / 2}
                </span>
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Prompt Sections */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Pair Comparison Prompt */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Pair Comparison Prompt</CardTitle>
            <CardDescription>For comparing two different clauses</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={pairPrompt}
              onChange={(e) => dispatch(setPairPrompt(e.target.value))}
              placeholder="Enter pair comparison prompt..."
              className="min-h-[200px] font-mono text-sm"
              disabled={isComparing}
            />
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">{pairPrompt.length} characters</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => dispatch(resetPairPrompt())}
                disabled={isComparing}
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Reset to Default
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Self-Check Prompt */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Self-Check Prompt</CardTitle>
            <CardDescription>For checking a clause against itself</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={selfPrompt}
              onChange={(e) => dispatch(setSelfPrompt(e.target.value))}
              placeholder="Enter self-check prompt..."
              className="min-h-[200px] font-mono text-sm"
              disabled={isComparing}
            />
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">{selfPrompt.length} characters</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => dispatch(resetSelfPrompt())}
                disabled={isComparing}
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Reset to Default
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-4">
        {!isComparing ? (
          <>
            <Button
              onClick={handleStartComparison}
              size="lg"
              className="flex-1"
            >
              <Zap className="w-5 h-5 mr-2" />
              Compare All Clauses
            </Button>
            <Button
              onClick={handleClearAll}
              variant="outline"
              size="lg"
            >
              <Trash2 className="w-5 h-5 mr-2" />
              Clear All
            </Button>
          </>
        ) : (
          <>
            <Button
              onClick={handleStopComparison}
              variant="destructive"
              size="lg"
              className="flex-1"
            >
              <AlertTriangle className="w-5 h-5 mr-2" />
              Stop Comparison
            </Button>
            <div className="text-muted-foreground text-sm flex items-center">
              Comparing... ({completedCount}/{totalComparisons})
            </div>
          </>
        )}
      </div>

      {/* Progress Section */}
      {isComparing && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Progress</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Progress value={progress} className="h-2" />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>Completed: {completedCount} / {totalComparisons}</span>
              <span>{Math.round(progress)}%</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error Display */}
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Results Section */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center justify-between">
              <span>Results ({results.length} / {totalComparisons})</span>
              <div className="flex gap-2">
                <Badge variant="destructive">{conflictCount} Conflicts</Badge>
                <Badge variant="default">{results.length - conflictCount} No Conflicts</Badge>
              </div>
            </CardTitle>
            <CardDescription>
              Real-time comparison results with performance metrics
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {results.map((result, idx) => (
              <Card key={idx} className="border-l-4" style={{
                borderLeftColor: result.conflict ? '#ef4444' : '#10b981'
              }}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">
                        {result.is_self_check ? (
                          <>Clause {result.clause_i_index + 1} (Self-Check)</>
                        ) : (
                          <>Clause {result.clause_i_index + 1} ↔ Clause {result.clause_j_index + 1}</>
                        )}
                      </span>
                      {result.is_self_check && (
                        <Badge variant="secondary">Self-Consistency</Badge>
                      )}
                      <Badge variant={result.conflict ? 'destructive' : 'default'}>
                        {result.conflict ? (
                          <>
                            <AlertTriangle className="w-3 h-3 mr-1" />
                            Conflict
                          </>
                        ) : (
                          <>
                            <CheckCircle className="w-3 h-3 mr-1" />
                            No Conflict
                          </>
                        )}
                      </Badge>
                      {result.severity !== 'Unknown' && result.severity !== 'Error' && (
                        <Badge variant="outline">{result.severity} Severity</Badge>
                      )}
                    </div>
                    <div className="flex gap-3 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {result.performance.total_time.toFixed(2)}s
                      </div>
                      <div className="flex items-center gap-1">
                        <Zap className="w-3 h-3" />
                        {result.performance.tokens_per_second.toFixed(1)} tok/s
                      </div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm whitespace-pre-wrap">{result.explanation}</p>
                  {result.performance.time_to_first_token && (
                    <div className="mt-3 pt-3 border-t text-xs text-muted-foreground">
                      <span className="font-semibold">Performance:</span> First token in{' '}
                      {result.performance.time_to_first_token.toFixed(2)}s | {result.performance.total_tokens} tokens generated
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
