// Upload and Extract UI Component
'use client';

import React, { useState, useRef, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '@/lib/store';
import {
  uploadStarted,
  progressUpdate,
  uploadCompleted,
  uploadFailed,
  uploadReset,
  setContractDetails,
  setClausesList,
  toggleClauseSelection,
  selectAllClauses,
  clearClauseSelection,
  setSearchQuery,
} from '@/features/upload/uploadSlice';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Upload,
  FileText,
  CheckCircle2,
  XCircle,
  Loader2,
  Search,
  Send,
} from 'lucide-react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export default function UploadAndExtract() {
  const dispatch = useDispatch();
  const uploadState = useSelector((state: RootState) => state.upload);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  // Fetch contract details
  const fetchContractDetails = useCallback(async (contractId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/contracts/${contractId}`);
      if (response.ok) {
        const data = await response.json();
        dispatch(setContractDetails(data));
      }
    } catch (error) {
      console.error('Failed to fetch contract details:', error);
    }
  }, [dispatch]);

  // Fetch clauses
  const fetchClauses = useCallback(async (contractId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/contracts/${contractId}/clauses`);
      if (response.ok) {
        const data = await response.json();
        dispatch(setClausesList(data.clauses));
      }
    } catch (error) {
      console.error('Failed to fetch clauses:', error);
    }
  }, [dispatch]);

  // Upload file with SSE progress tracking
  const uploadFile = useCallback(async (file: File) => {
    dispatch(uploadStarted());

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE_URL}/contracts/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      // Read SSE stream
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
            try {
              const eventData = JSON.parse(line.substring(6));
              dispatch(progressUpdate(eventData));

              // Check for completion
              if (eventData.stage === 'PROCESSING_COMPLETED') {
                dispatch(uploadCompleted({ contractId: eventData.data.contract_id }));
                
                // Fetch contract details and clauses
                fetchContractDetails(eventData.data.contract_id);
                fetchClauses(eventData.data.contract_id);
              } else if (eventData.stage === 'ERROR') {
                dispatch(uploadFailed(eventData.message));
              }
            } catch (e) {
              console.error('Failed to parse SSE event:', e);
            }
          }
        }
      }
    } catch (error: unknown) {
      console.error('Upload error:', error);
      const errorMessage = error instanceof Error ? error.message : 'Upload failed';
      dispatch(uploadFailed(errorMessage));
    }
  }, [dispatch, fetchContractDetails, fetchClauses]);

  // Handle file selection
  const handleFileSelect = useCallback((file: File) => {
    if (!file) return;

    // Validate file type
    const validTypes = ['.pdf', '.docx', '.doc', '.txt'];
    const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
    
    if (!validTypes.includes(fileExt)) {
      alert(`Unsupported file type: ${fileExt}. Supported: ${validTypes.join(', ')}`);
      return;
    }

    // Validate file size (max 50MB)
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      alert(`File too large: ${(file.size / 1024 / 1024).toFixed(2)}MB (max: 50MB)`);
      return;
    }

    // Start upload
    uploadFile(file);
  }, [uploadFile]);

  // Drag and drop handlers
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  // Filter clauses based on search
  const filteredClauses = uploadState.clauses.filter((clause) => {
    const matchesSearch = 
      clause.clause_number.toLowerCase().includes(uploadState.searchQuery.toLowerCase()) ||
      clause.content.toLowerCase().includes(uploadState.searchQuery.toLowerCase());
    return matchesSearch;
  });

  // Send clauses to Testing Lab
  const sendToTestingLab = () => {
    if (uploadState.selectedClauseIds.length === 0) {
      alert('Please select at least one clause');
      return;
    }

    // Get selected clauses
    const selectedClauses = uploadState.clauses.filter(c => 
      uploadState.selectedClauseIds.includes(c.id)
    );

    // Store in localStorage for Testing Lab to pick up
    localStorage.setItem('testingLabClauses', JSON.stringify(selectedClauses));
    
    // Navigate to Testing Lab (you can adjust this based on your routing)
    alert(`${selectedClauses.length} clauses ready for Testing Lab! Switch to the "Testing Lab" tab.`);
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold">Upload & Extract</h2>
          <p className="text-muted-foreground mt-1">
            Upload a contract and automatically extract clauses for analysis
          </p>
        </div>
        {uploadState.contractId && (
          <Button onClick={() => dispatch(uploadReset())} variant="outline">
            Upload New Contract
          </Button>
        )}
      </div>

      {/* Upload Area */}
      {!uploadState.isUploading && !uploadState.contractId && (
        <Card>
          <CardContent className="pt-6">
            <div
              className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                dragActive
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-primary/50'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">
                Drop your contract here or click to browse
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                Supported formats: PDF, DOCX, DOC, TXT (max 50MB)
              </p>
              <Button onClick={() => fileInputRef.current?.click()}>
                Select File
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".pdf,.docx,.doc,.txt"
                onChange={(e) => {
                  if (e.target.files?.[0]) {
                    handleFileSelect(e.target.files[0]);
                  }
                }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Progress Tracker */}
      {uploadState.isUploading && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="animate-spin h-5 w-5" />
              Processing Contract
            </CardTitle>
            <CardDescription>{uploadState.statusMessage}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={uploadState.uploadProgress} className="w-full" />
            
            {/* Progress Timeline */}
            <ScrollArea className="h-[300px] rounded border p-4">
              <div className="space-y-3">
                {uploadState.progressEvents.map((event, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {event.stage.includes('ERROR') ? (
                        <XCircle className="h-4 w-4 text-destructive" />
                      ) : event.stage.includes('COMPLETED') || event.stage.includes('FINISHED') ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : (
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      )}
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{event.message}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                    <Badge variant="outline">{event.progress}%</Badge>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {/* Error Display */}
      {uploadState.error && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <XCircle className="h-5 w-5" />
              Processing Failed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">{uploadState.error}</p>
            <Button
              onClick={() => dispatch(uploadReset())}
              variant="outline"
              className="mt-4"
            >
              Try Again
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Contract Details & Clause List */}
      {uploadState.contractDetails && uploadState.showClauseList && (
        <div className="space-y-4">
          {/* Contract Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                Contract Processed Successfully
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Filename</p>
                  <p className="font-medium">{uploadState.contractDetails.filename}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Clauses Extracted</p>
                  <p className="font-medium">{uploadState.contractDetails.clause_count}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Parties Identified</p>
                  <p className="font-medium">{uploadState.contractDetails.parties.length}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge variant="outline" className="text-green-500">
                    {uploadState.contractDetails.status}
                  </Badge>
                </div>
              </div>
              
              {/* Parties */}
              {uploadState.contractDetails.parties.length > 0 && (
                <div className="mt-4">
                  <p className="text-sm text-muted-foreground mb-2">Contract Parties:</p>
                  <div className="flex flex-wrap gap-2">
                    {uploadState.contractDetails.parties.map((party) => (
                      <Badge key={party.id} variant="secondary">
                        {party.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Clause Selection */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Select Clauses for Testing Lab</CardTitle>
                  <CardDescription>
                    Choose clauses to analyze ({uploadState.selectedClauseIds.length} selected)
                  </CardDescription>
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={() => dispatch(selectAllClauses())}
                    variant="outline"
                    size="sm"
                  >
                    Select All
                  </Button>
                  <Button
                    onClick={() => dispatch(clearClauseSelection())}
                    variant="outline"
                    size="sm"
                  >
                    Clear
                  </Button>
                  <Button
                    onClick={sendToTestingLab}
                    disabled={uploadState.selectedClauseIds.length === 0}
                    size="sm"
                  >
                    <Send className="h-4 w-4 mr-2" />
                    Send to Testing Lab
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* Search */}
              <div className="mb-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search clauses by number or content..."
                    value={uploadState.searchQuery}
                    onChange={(e) => dispatch(setSearchQuery(e.target.value))}
                    className="pl-10"
                  />
                </div>
              </div>

              {/* Clause List */}
              <ScrollArea className="h-[500px] rounded border">
                <div className="p-4 space-y-4">
                  {filteredClauses.map((clause) => (
                    <div
                      key={clause.id}
                      className="flex items-start gap-3 p-3 rounded border hover:bg-accent/50 transition-colors"
                    >
                      <Checkbox
                        checked={uploadState.selectedClauseIds.includes(clause.id)}
                        onCheckedChange={() => dispatch(toggleClauseSelection(clause.id))}
                        className="mt-1"
                      />
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge variant="outline">{clause.clause_number}</Badge>
                          <FileText className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <p className="text-sm line-clamp-3">{clause.content}</p>
                        
                        {/* Sub-clauses */}
                        {clause.sub_clauses && clause.sub_clauses.length > 0 && (
                          <div className="mt-2 ml-4 space-y-2">
                            {clause.sub_clauses.map((sub) => (
                              <div key={sub.id} className="text-sm text-muted-foreground">
                                <Badge variant="secondary" className="text-xs mr-2">
                                  {sub.clause_number}
                                </Badge>
                                <span className="line-clamp-2">{sub.content}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  
                  {filteredClauses.length === 0 && (
                    <div className="text-center text-muted-foreground py-12">
                      No clauses found matching your search
                    </div>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
