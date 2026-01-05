/**
 * Batch Comparison Component
 * 
 * Compare one source clause against multiple target clauses (1 → N).
 * Results are streamed and displayed in real-time.
 * 
 * UI Design: Dynamic input boxes for each comparison clause
 */

'use client'

import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '@/lib/store';
import {
  setSourceClause,
  setTargetClauses,
  addTargetClause,
  removeTargetClause,
  updateTargetClause,
  setPrompt,
  resetPrompt,
  startComparison,
  addResult,
  completeComparison,
  setError,
  clearAll,
} from '@/features/batchComparison/batchComparisonSlice';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { 
  Loader2, 
  GitCompare, 
  RotateCcw, 
  Trash2, 
  AlertTriangle, 
  CheckCircle,
  Clock,
  Zap,
  Plus,
  X,
  ArrowRight
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';

export default function BatchComparisonPage() {
  const dispatch = useDispatch<AppDispatch>();
  const {
    sourceClause,
    targetClauses,
    prompt,
    results,
    isComparing,
    totalClauses,
    completedCount,
    error
  } = useSelector((state: RootState) => state.batchComparison);
  
  const { toast } = useToast();
  
  // Initialize with one empty target clause if none exist
  useEffect(() => {
    if (targetClauses.length === 0) {
      dispatch(addTargetClause(''));
    }
  }, [dispatch, targetClauses.length]);

  const handleAddClause = () => {
    if (targetClauses.length >= 100) {
      toast({
        title: "Maximum Reached",
        description: "You can compare up to 100 clauses at once.",
        variant: "destructive",
      });
      return;
    }
    dispatch(addTargetClause(''));
  };

  const handleRemoveClause = (index: number) => {
    if (targetClauses.length === 1) {
      toast({
        title: "Cannot Remove",
        description: "At least one comparison clause is required.",
        variant: "destructive",
      });
      return;
    }
    dispatch(removeTargetClause(index));
  };

  const handleUpdateClause = (index: number, value: string) => {
    dispatch(updateTargetClause({ index, value }));
  };

  const handleStartComparison = async () => {
    if (!sourceClause.trim()) {
      toast({
        title: "Missing Source Clause",
        description: "Please provide a source clause to compare.",
        variant: "destructive",
      });
      return;
    }

    // Filter out empty target clauses
    const validClauses = targetClauses.filter(c => c.trim().length > 0);

    if (validClauses.length === 0) {
      toast({
        title: "Missing Target Clauses",
        description: "Please provide at least one target clause.",
        variant: "destructive",
      });
      return;
    }

    dispatch(setTargetClauses(validClauses));
    dispatch(startComparison(validClauses.length));

    // Start SSE connection
    try {
      const response = await fetch('/api/v1/compare/batch', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          source_clause: sourceClause,
          target_clauses: validClauses,
          prompt: prompt,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));

            if (data.type === 'result') {
              dispatch(addResult(data.data));
            } else if (data.type === 'complete') {
              dispatch(completeComparison());
              toast({
                title: "Comparison Complete",
                description: `All ${validClauses.length} comparisons finished successfully.`,
              });
            } else if (data.type === 'error') {
              dispatch(setError(data.message));
              toast({
                title: "Error",
                description: data.message,
                variant: "destructive",
              });
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to compare clauses';
      dispatch(setError(message));
      toast({
        title: "Comparison Failed",
        description: message,
        variant: "destructive",
      });
    }
  };

  const handleClearAll = () => {
    dispatch(clearAll());
    // Add back one empty clause
    dispatch(addTargetClause(''));
    toast({
      title: "Cleared",
      description: "All inputs and results have been cleared.",
    });
  };

  const progress = totalClauses > 0 ? (completedCount / totalClauses) * 100 : 0;

  return (
    <div className="container mx-auto py-10 space-y-8 max-w-7xl">
      <div className="space-y-2">
        <h1 className="text-4xl font-bold flex items-center gap-3">
          <GitCompare className="w-10 h-10 text-primary" />
          Dynamic Clause Comparison (A → N)
        </h1>
        <p className="text-muted-foreground">
          Compare Clause A against multiple clauses independently. Each comparison is a separate analysis: A ↔ 1, A ↔ 2, A ↔ 3, ...
        </p>
      </div>

      {/* Input Section */}
      <div className="space-y-6">
        {/* Clause A (Source) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold">
                A
              </div>
              Reference Clause
            </CardTitle>
            <CardDescription>This clause will be compared against each clause below</CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea
              value={sourceClause}
              onChange={(e) => dispatch(setSourceClause(e.target.value))}
              placeholder="Enter Clause A here (the reference clause for all comparisons)..."
              className="min-h-[150px] font-mono text-sm"
              disabled={isComparing}
            />
            <div className="text-xs text-muted-foreground mt-2">
              {sourceClause.length} characters
            </div>
          </CardContent>
        </Card>

        {/* Comparison Clauses */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Comparison Clauses</CardTitle>
                <CardDescription>Each clause will be compared independently with Clause A</CardDescription>
              </div>
              <Button
                onClick={handleAddClause}
                disabled={isComparing || targetClauses.length >= 100}
                size="sm"
                variant="outline"
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Clause
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {targetClauses.map((clause, index) => (
              <div key={index} className="space-y-2">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground min-w-[100px]">
                    <div className="w-7 h-7 rounded-full bg-secondary text-secondary-foreground flex items-center justify-center font-semibold text-xs">
                      {index + 1}
                    </div>
                    <ArrowRight className="w-4 h-4" />
                    <span className="font-medium">A ↔ {index + 1}</span>
                  </div>
                  <div className="flex-1">
                    <Textarea
                      value={clause}
                      onChange={(e) => handleUpdateClause(index, e.target.value)}
                      placeholder={`Enter clause ${index + 1} to compare with Clause A...`}
                      className="min-h-[100px] font-mono text-sm"
                      disabled={isComparing}
                    />
                  </div>
                  <Button
                    onClick={() => handleRemoveClause(index)}
                    disabled={isComparing || targetClauses.length === 1}
                    size="icon"
                    variant="ghost"
                    className="shrink-0"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
                <div className="text-xs text-muted-foreground ml-[115px]">
                  {clause.length} characters
                </div>
              </div>
            ))}
            
            <div className="pt-2 border-t">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  Total comparisons: <span className="font-semibold">{targetClauses.filter(c => c.trim()).length}</span>
                </span>
                <span className="text-muted-foreground">
                  Each clause is compared independently with Clause A
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Prompt Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Analysis Prompt</CardTitle>
          <CardDescription>Customize how the AI analyzes each comparison</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={prompt}
            onChange={(e) => dispatch(setPrompt(e.target.value))}
            placeholder="Enter your analysis prompt..."
            className="min-h-[150px] font-mono text-sm"
            disabled={isComparing}
          />
          <div className="flex justify-between items-center">
            <span className="text-xs text-muted-foreground">{prompt.length} characters</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => dispatch(resetPrompt())}
              disabled={isComparing}
            >
              <RotateCcw className="w-4 h-4 mr-2" />
              Reset to Default
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <div className="flex gap-4">
        <Button
          onClick={handleStartComparison}
          disabled={isComparing}
          size="lg"
          className="flex-1"
        >
          {isComparing ? (
            <>
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              Comparing... ({completedCount}/{totalClauses})
            </>
          ) : (
            <>
              <Zap className="w-5 h-5 mr-2" />
              Start Batch Comparison
            </>
          )}
        </Button>
        <Button
          onClick={handleClearAll}
          disabled={isComparing}
          variant="outline"
          size="lg"
        >
          <Trash2 className="w-5 h-5 mr-2" />
          Clear All
        </Button>
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
              <span>Completed: {completedCount} / {totalClauses}</span>
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
            <CardTitle className="text-lg">
              Results ({results.length} / {totalClauses})
            </CardTitle>
            <CardDescription>
              Real-time comparison results with performance metrics
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {results.map((result) => (
              <Card key={result.index} className="border-l-4" style={{
                borderLeftColor: result.conflict ? '#ef4444' : '#10b981'
              }}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">Clause #{result.index + 1}</span>
                      <Badge variant={result.conflict ? 'destructive' : 'default'}>
                        {result.conflict ? (
                          <>
                            <AlertTriangle className="w-3 h-3 mr-1" />
                            Conflict Detected
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
