# -*- coding: utf-8 -*-
import pytesseract
from PIL import Image
import logging
from typing import Dict, List, Optional, Any
import sys

logger = logging.getLogger(__name__)


class OCREngine:
    """Tesseract OCR wrapper for text extraction"""

    def __init__(self, tesseract_cmd: str, language: str = "tur+eng"):
        """
        Initialize OCR engine

        Args:
            tesseract_cmd: Path to tesseract executable
            language: OCR language(s) - default Turkish + English
        """
        self.language = language

        # Set Tesseract command path
        if tesseract_cmd and tesseract_cmd != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # Verify Tesseract is installed
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract versiyonu: {version}")
        except Exception as e:
            logger.error(f"Tesseract bulunamadı: {str(e)}")
            logger.error("Tesseract kurulumu gerekli: https://github.com/tesseract-ocr/tesseract")

    def extract_text(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text from image with detailed information

        Args:
            image_path: Path to image file

        Returns:
            Dictionary containing:
                - text: Full extracted text
                - words_with_bbox: List of words with bounding boxes
                - confidence_scores: Confidence score for each word
                - average_confidence: Overall confidence
        """
        try:
            # Open image
            image = Image.open(image_path)

            # Extract text
            text = pytesseract.image_to_string(
                image,
                lang=self.language,
                config='--psm 3'  # Fully automatic page segmentation
            )

            # Extract detailed data (word-level)
            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                output_type=pytesseract.Output.DICT
            )

            # Process word-level data
            words_with_bbox = []
            confidence_scores = {}
            total_conf = 0
            word_count = 0

            for i in range(len(data['text'])):
                word = data['text'][i].strip()

                if word:  # Only process non-empty words
                    conf = int(data['conf'][i])

                    if conf > 0:  # Only include words with valid confidence
                        word_data = {
                            'word': word,
                            'confidence': conf / 100.0,  # Normalize to 0-1
                            'bbox': {
                                'x': data['left'][i],
                                'y': data['top'][i],
                                'w': data['width'][i],
                                'h': data['height'][i]
                            },
                            'line_num': data['line_num'][i],
                            'block_num': data['block_num'][i]
                        }

                        words_with_bbox.append(word_data)
                        confidence_scores[word] = conf / 100.0

                        total_conf += conf
                        word_count += 1

            # Calculate average confidence
            avg_confidence = (total_conf / word_count / 100.0) if word_count > 0 else 0.0

            result = {
                'text': text.strip(),
                'words_with_bbox': words_with_bbox,
                'confidence_scores': confidence_scores,
                'average_confidence': avg_confidence,
                'word_count': word_count
            }

            logger.info(
                f"OCR tamamlandı: {word_count} kelime, "
                f"ortalama güven: {avg_confidence:.2f}"
            )

            return result

        except Exception as e:
            logger.error(f"OCR hatası {image_path}: {str(e)}")
            return {
                'text': '',
                'words_with_bbox': [],
                'confidence_scores': {},
                'average_confidence': 0.0,
                'word_count': 0,
                'error': str(e)
            }

    def extract_text_simple(self, image_path: str) -> str:
        """
        Simple text extraction (just the text)

        Args:
            image_path: Path to image file

        Returns:
            Extracted text string
        """
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang=self.language)
            return text.strip()
        except Exception as e:
            logger.error(f"OCR hatası {image_path}: {str(e)}")
            return ""

    def extract_structured_data(self, image_path: str) -> Dict[str, List[str]]:
        """
        Extract text organized by lines and blocks

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with text organized by structure
        """
        try:
            image = Image.open(image_path)

            # Get detailed OCR data
            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                output_type=pytesseract.Output.DICT
            )

            # Organize by blocks and lines
            blocks = {}
            current_block = None
            current_line = None

            for i in range(len(data['text'])):
                word = data['text'][i].strip()

                if not word:
                    continue

                block_num = data['block_num'][i]
                line_num = data['line_num'][i]

                # Initialize block if needed
                if block_num not in blocks:
                    blocks[block_num] = {}

                # Initialize line if needed
                if line_num not in blocks[block_num]:
                    blocks[block_num][line_num] = []

                # Add word to line
                blocks[block_num][line_num].append(word)

            # Convert to structured format
            structured = {
                'blocks': [],
                'lines': [],
                'all_text': []
            }

            for block_num in sorted(blocks.keys()):
                block_lines = []
                for line_num in sorted(blocks[block_num].keys()):
                    line_text = ' '.join(blocks[block_num][line_num])
                    block_lines.append(line_text)
                    structured['lines'].append(line_text)

                block_text = '\n'.join(block_lines)
                structured['blocks'].append(block_text)
                structured['all_text'].append(block_text)

            return structured

        except Exception as e:
            logger.error(f"Yapılandırılmış OCR hatası {image_path}: {str(e)}")
            return {'blocks': [], 'lines': [], 'all_text': []}

    def get_available_languages(self) -> List[str]:
        """
        Get list of available Tesseract languages

        Returns:
            List of language codes
        """
        try:
            langs = pytesseract.get_languages()
            return langs
        except Exception as e:
            logger.error(f"Dil listesi alınamadı: {str(e)}")
            return []
