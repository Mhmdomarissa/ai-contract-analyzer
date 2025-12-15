"""
Advanced Document Extractors: PyMuPDF (primary, fast, reliable)
Simplified based on test results - PyMuPDF provides best results
"""
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger(__name__)


class MultiMethodExtractor:
    """
    Multi-method extractor - Uses PyMuPDF (fast, reliable).
    Based on testing: PyMuPDF provides best balance of speed and quality.
    """
    
    def __init__(self, use_gpu: bool = False):
        """
        Initialize extractor.
        
        Args:
            use_gpu: Not used (kept for compatibility)
        """
        logger.info("=" * 70)
        logger.info("Initializing MultiMethodExtractor...")
        
        # Import PyMuPDF (primary extractor)
        try:
            import fitz
            self.pymupdf_available = True
            logger.info("✅ PyMuPDF available (primary extractor)")
        except ImportError:
            self.pymupdf_available = False
            logger.error("❌ PyMuPDF not available - this is required!")
        
        logger.info(f"Extractor status: PyMuPDF={self.pymupdf_available}")
        logger.info("=" * 70)
    
    def extract_with_consensus(
        self, 
        pdf_path: str,
        prefer_marker: bool = False,  # Not used (kept for compatibility)
        fast_mode: bool = True  # Not used (kept for compatibility)
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text using PyMuPDF (fast, reliable).
        
        Args:
            pdf_path: Path to PDF file
            prefer_marker: Not used (kept for compatibility)
            fast_mode: Not used (kept for compatibility)
            
        Returns:
            Tuple of (extracted_text, metadata)
        """
        logger.info(f"Starting extraction for: {pdf_path}")
        
        if not self.pymupdf_available:
            logger.error("❌ PyMuPDF not available")
            return "", {'error': 'PyMuPDF not available', 'method': 'none'}
        
        try:
            logger.info("Extracting with PyMuPDF (fast, reliable)...")
            import fitz
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            page_count = len(doc)
            doc.close()
            
            if text and len(text.strip()) > 100:
                logger.info(f"✅ PyMuPDF extraction successful: {len(text)} chars from {page_count} pages")
                return text, {
                    'method': 'pymupdf',
                    'confidence': 0.88,
                    'metadata': {'pages': page_count}
                }
            else:
                logger.warning(f"⚠️ PyMuPDF extracted insufficient text ({len(text)} chars)")
                return text, {
                    'method': 'pymupdf',
                    'confidence': 0.5,
                    'metadata': {'pages': page_count, 'warning': 'Low text content'}
                }
        except Exception as e:
            logger.error(f"❌ PyMuPDF extraction failed: {e}")
            return "", {'error': str(e), 'method': 'pymupdf'}
