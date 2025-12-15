"use client"

import { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '@/lib/store';
import { uploadContract, extractClauses, detectConflicts } from '@/features/contract/contractSlice';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Upload, FileText, AlertTriangle, Code, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

export default function ContractAnalysisPage() {
  const dispatch = useDispatch<AppDispatch>();
  const { contract, clauses, conflicts, loadingStep, currentStep, clauseJob } = useSelector((state: RootState) => state.contract);
  const { toast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [showJsonModal, setShowJsonModal] = useState(false);

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name);

    try {
      await dispatch(uploadContract(formData)).unwrap();
      toast({ title: "Success", description: "File uploaded and parsed successfully." });
    } catch (error) {
      toast({ title: "Error", description: getErrorMessage(error, "Upload failed."), variant: "destructive" });
    }
  };

  const handleExtract = async () => {
    if (!contract) return;
    try {
      await dispatch(extractClauses(contract.id)).unwrap();
      toast({ title: "Success", description: "Clauses extracted successfully." });
    } catch (error) {
      toast({ title: "Error", description: getErrorMessage(error, "Extraction failed."), variant: "destructive" });
    }
  };

  const handleDetect = async () => {
    if (!contract) return;
    try {
      await dispatch(detectConflicts(contract.id)).unwrap();
      toast({ title: "Success", description: "Conflicts detected successfully." });
    } catch (error) {
      toast({ title: "Error", description: getErrorMessage(error, "Conflict detection failed."), variant: "destructive" });
    }
  };


  return (
    <div className="container mx-auto py-10 space-y-8 max-w-4xl">
      <h1 className="text-3xl font-bold mb-8">AI Contract Analyzer</h1>

      {/* Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="w-5 h-5" /> Upload Contract
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Input type="file" onChange={handleFileChange} accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" />
            <Button 
              onClick={handleUpload} 
              disabled={!file || loadingStep === 'upload'}
            >
              {loadingStep === 'upload' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Upload & Parse
            </Button>
          </div>
          {contract?.latest_version && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Latest version #{contract.latest_version.version_number} uploaded on{' '}
                {new Date(contract.latest_version.created_at).toLocaleString()}
              </p>
              
              {/* Display Parsed Text */}
              {contract.latest_version.parsed_text && (
                <div className="mt-4">
                  <h3 className="font-semibold mb-2">Parsed Document Text</h3>
                  <div className="max-h-[500px] overflow-y-auto border rounded-md p-4 bg-muted/50">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {contract.latest_version.parsed_text}
                    </p>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Total characters: {contract.latest_version.parsed_text.length.toLocaleString()}
                  </p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extract Clauses Section */}
      <Card className={currentStep === 'upload' ? 'opacity-50 pointer-events-none' : ''}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5" /> Extract Clauses
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2 flex-wrap">
          <Button 
            onClick={handleExtract} 
            disabled={loadingStep === 'extract' || !contract}
            className="w-full sm:w-auto"
          >
            {loadingStep === 'extract' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Extract Clauses
          </Button>
            <Button 
              onClick={() => setShowJsonModal(true)} 
              disabled={clauses.length === 0}
              variant="outline"
              className="w-full sm:w-auto"
            >
              <Code className="mr-2 h-4 w-4" />
              View JSON Response
            </Button>
          </div>
          {clauseJob && (
            <div className="text-sm text-muted-foreground">
              Clause extraction status: <span className="font-medium">{clauseJob.status}</span>
              {clauseJob.error_message && (
                <span className="text-destructive ml-2">{clauseJob.error_message}</span>
              )}
            </div>
          )}
          
          {clauses.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold">Extracted Clauses ({clauses.length})</h3>
                {(() => {
                  if (clauses.length > 0) {
                    return (
                      <div className="flex gap-4 text-sm">
                        <span className="text-muted-foreground">
                          Total Clauses: {clauses.length}
                        </span>
                      </div>
                    );
                  }
                  return null;
                })()}
              </div>
              <div className="max-h-[600px] overflow-y-auto border rounded-md p-4 bg-muted/50 space-y-3">
                {clauses.map((clause) => {
                  const clauseLabel = clause.clause_number ?? String(clause.order_index + 1);
                  const analysisStatus = clause.analysis_status;
                  
                  return (
                    <div key={clause.id} className="p-3 bg-background rounded border">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-primary">
                          Clause #{clauseLabel}
                        </span>
                        </div>
                        {clause.heading && (
                          <span className="text-sm font-medium text-muted-foreground">{clause.heading}</span>
                        )}
                      </div>
                      
                      {clause.is_bilingual && clause.arabic_text ? (
                        <div className="space-y-3">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-semibold text-blue-600 uppercase">English</span>
                            </div>
                            <p className="text-sm whitespace-pre-wrap leading-relaxed bg-blue-50 dark:bg-blue-950/20 p-2 rounded border border-blue-200 dark:border-blue-800">
                              {clause.text}
                            </p>
                          </div>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-semibold text-green-600 uppercase">Arabic</span>
                            </div>
                            <p className="text-sm whitespace-pre-wrap leading-relaxed bg-green-50 dark:bg-green-950/20 p-2 rounded border border-green-200 dark:border-green-800" dir="rtl">
                              {clause.arabic_text}
                            </p>
                          </div>
                        </div>
                      ) : (
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{clause.text}</p>
                      )}
                      {clause.language && (
                        <span className="text-xs text-muted-foreground mt-2 inline-block">
                          Language: {clause.language}
                          {clause.is_bilingual && <span className="ml-1 text-blue-600">(Bilingual)</span>}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detect Conflicts Section */}
      <Card className={['upload', 'extract'].includes(currentStep) ? 'opacity-50 pointer-events-none' : ''}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" /> Detect Conflicts
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button 
            onClick={handleDetect} 
            disabled={loadingStep === 'detect' || clauses.length === 0}
            className="w-full sm:w-auto"
          >
            {loadingStep === 'detect' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {loadingStep === 'detect' ? 'Analyzing...' : 'Detect Conflicts'}
          </Button>

          {loadingStep === 'detect' && (
            <div className="text-sm text-muted-foreground mt-2">
              Analyzing clauses... Results will appear as they're processed.
            </div>
          )}

          {/* JSON Modal */}
          {showJsonModal && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
              <div className="bg-background rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col">
                <div className="flex items-center justify-between p-4 border-b">
                  <h2 className="text-xl font-semibold">JSON Response - All Clauses with IDs</h2>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => setShowJsonModal(false)}
                  >
                    ✕
                  </Button>
                </div>
                <div className="flex-1 overflow-auto p-4">
                  <pre className="bg-muted p-4 rounded-md text-xs overflow-auto max-h-[70vh]">
                    {JSON.stringify(clauses, null, 2)}
                  </pre>
                </div>
                <div className="p-4 border-t flex justify-end gap-2">
                  <Button 
                    variant="outline"
                    onClick={() => {
                      navigator.clipboard.writeText(JSON.stringify(clauses, null, 2));
                      toast({ title: "Copied", description: "JSON copied to clipboard" });
                    }}
                  >
                    Copy JSON
                  </Button>
                  <Button onClick={() => setShowJsonModal(false)}>
                    Close
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Conflicts Between Clauses Section */}
          {conflicts.length > 0 && (
            <div className="mt-6">
              <h3 className="font-semibold text-lg mb-4">Conflicts Between Clauses ({conflicts.length})</h3>
              <div className="max-h-[600px] overflow-y-auto space-y-4">
                {conflicts.map((conflict, idx) => (
                  <div key={conflict.id || idx} className="p-4 bg-background rounded-lg border shadow-sm">
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-semibold text-xs uppercase px-3 py-1 rounded bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-100">
                        {conflict.severity} {conflict.type || 'CONFLICT'}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(conflict.created_at).toLocaleString()}
                      </span>
                    </div>
                    
                    <p className="text-sm mb-4 font-medium">{conflict.summary}</p>
                    
                    {conflict.explanation && (
                      <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-950/20 rounded-lg border border-blue-200 dark:border-blue-900">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-sm font-semibold text-blue-800 dark:text-blue-200">💡 Suggested Resolution:</span>
                        </div>
                        <p className="text-sm text-blue-700 dark:text-blue-300">{conflict.explanation}</p>
                      </div>
                    )}
                    
                    {/* Show full clause texts */}
                    <div className="space-y-3">
                      <div className="bg-red-50 dark:bg-red-950/20 p-4 rounded-lg border border-red-200 dark:border-red-900">
                        <div className="font-semibold text-red-900 dark:text-red-100 mb-2 flex items-center gap-2">
                          <span className="bg-red-200 dark:bg-red-900 px-2 py-1 rounded text-xs">
                            Clause {conflict.left_clause?.clause_number || conflict.left_clause?.id}
                          </span>
                          {conflict.left_clause?.heading && (
                            <span className="text-sm font-normal text-red-700 dark:text-red-300">
                              {conflict.left_clause.heading}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-red-800 dark:text-red-200 whitespace-pre-wrap leading-relaxed">
                          {conflict.left_clause?.text || 'Text not available'}
                        </p>
                      </div>
                      
                      <div className="bg-orange-50 dark:bg-orange-950/20 p-4 rounded-lg border border-orange-200 dark:border-orange-900">
                        <div className="font-semibold text-orange-900 dark:text-orange-100 mb-2 flex items-center gap-2">
                          <span className="bg-orange-200 dark:bg-orange-900 px-2 py-1 rounded text-xs">
                            Clause {conflict.right_clause?.clause_number || conflict.right_clause?.id}
                          </span>
                          {conflict.right_clause?.heading && (
                            <span className="text-sm font-normal text-orange-700 dark:text-orange-300">
                              {conflict.right_clause.heading}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-orange-800 dark:text-orange-200 whitespace-pre-wrap leading-relaxed">
                          {conflict.right_clause?.text || 'Text not available'}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

    </div>
  );
}
