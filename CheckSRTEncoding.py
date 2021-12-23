#!/usr/bin/python

import sys, getopt
import srt
import re
from html.parser import HTMLParser

def fix_encoding(string):
    
    #windows encoding
    #replace windows dash with 1 standard dash
    string = string.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x80\x9c', b'-')
    #replace windows EM DASH with 2 standard dashes
    string = string.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x80\x9d', b'--')
    #replace windows RIGHT SINGLE QUOTATION MARK with standard apostrophe
    string = string.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x84\xa2', b"'")

    #replace windows music note with EIA-608 encoded version
    string = string.replace(b'\xc3\xa2\xe2\x84\xa2\xc2\xaa', b'\x11\x37')
    
    #replace windows i carrot with EIA-608 encoded version
    string = string.replace(b'\xc3\x83\xc2\xae', b'\x11\x3d')

    #Extended Unicode character encoding
    #replace Unicode i carrot with EIA-608 encoded version
    string = string.replace(b'\xc3\xae', b'\x11\x3d')
    #replace Unicode RIGHT SINGLE QUOTATION MARK with standard apostrophe
    string = string.replace(b'\xe2\x80\x99', b"'")
    #replace Unicode EM DASH with 2 standard dashes
    string = string.replace(b'\xe2\x80\x94', b'--')
    #replace Unicode music note with EIA-608 encoded version
    string = string.replace(b'\xe2\x99\xaa', b'\x11\x37')

    #non-ascii character codes for EIA-608
    #Lower-case a with acute accent:  \x2A
    #Lower-case e with acute accent:  \x5C
    #Lower-case i with acute accent:  \x5E
    #Lower-case o with acute accent:  \x5F
    #Lower-case u with acute accent:  \x60
    #Lower-case c with cedilla:       \x7B
    #Division sign:                   \x7C
    #Upper-case N with tilde:         \x7D
    #Lower-case n with tilde:         \x7E
    #Solid block:                     \x7F
    return string

def check_EIA608_encoding(string):
    #replace CC control codes with valid ASCII character
    string = string.replace("\x11\x3d", "a")
    string = string.replace("\x11\x37", "a")
    #check for subset of ASCII that is supported by EIA 608
    result = re.search(r"[^a-zA-Z0-9 !\"#$%&')(+,-./:;<=>?@[]\n]", string)
    if not bool(result):
        return True
    else:
        return False

def replace_newlines(string):
    preamble_codes = [b"\x14\x70", b"\x14\x50", b"\x13\x70", b"\x13\x50",
                     b"\x10\x50", b"\x17\x70", b"\x17\x50", b"\x16\x70",
                     b"\x16\x50", b"\x15\x70", b"\x15\x50", b"\x12\x70",
                     b"\x12\x50", b"\x11\x70", b"\x11\x50"]

    lines = string.split(b'\n')
    
    reverse_lines = reversed(lines)
    pop_on_captions = b""
    for index, c in enumerate(reverse_lines):
        pop_on_captions =  preamble_codes[index] + preamble_codes[index] + c + pop_on_captions
            
    return pop_on_captions

def check_caption_length(string):
    lines = string.split('\n')
    for i in lines:
        if len(i) > 32:
            return False

    return True

class CaptionStyleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= False
        self.text = ""
        self.tag = ""
    def handle_starttag(self, tag, attrs):
        self.tag = tag
    def handle_endtag(self, tag):
        self.tag = ""
    def handle_data(self, d):
        italic_control_code = "\x11\x2E\x11\x2E"
        no_style_control_code = "\x11\x20\x11\x20"
        
        styled_caption = d
         
        if self.tag == 'i':
            #Style control codes display as space
            #so remove any preceding space character
            if self.text:
                if self.text[-1] == ' ':
                   self.text = self.text[:-1]
                   
            #italicize text inside the style tags       
            styled_caption = italic_control_code + styled_caption

            #italicize each line inside the style tags
            #this is for multiline italicized text
            styled_caption = styled_caption.replace('\n', '\n' + italic_control_code)

            #remove style at the end of tag
            #this is for styled text in the middle of a line
            styled_caption = styled_caption + no_style_control_code

        if (self.tag != 'i') and self.tag:
            print("Unknown style tag found")
            
        #Style control codes display as space
        #so remove any following space character
        if (self.text[-4:] == no_style_control_code) and (styled_caption[0] == ' '):
            styled_caption = styled_caption[1:]
            
        self.text = self.text + styled_caption

        
    def get_data(self):
        #dont need to set style at the end of a caption
        #so lets remove it
        no_style_control_code = "\x11\x20\x11\x20"
        if self.text[-4:] == no_style_control_code:
            self.text = self.text[:-4]
        return self.text

def add_style_codes(subtitle):
    s = CaptionStyleParser()
    s.feed(subtitle)
    return s.get_data()

def get_args(argv):

    if len(argv) == 0:
        print('Using default subtitle filename Subtitle.srt')
        return "Subtitle.srt"
    
    inputfile = ''
    try:
        opts, args = getopt.getopt(argv,"hs:",["subfile="])
    except getopt.GetoptError:
        print("Usage: CheckSRTEncoding.py -s <subtitle file>")
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('Usage: CheckSRTEncoding.py -s <subtitle file>')
            sys.exit()
        elif opt in ("-s", "--subfile"):
            inputfile = arg
            
    print('Input file is ' + inputfile)
    return inputfile
    
if __name__ == "__main__":  
    inputfile = get_args(sys.argv[1:])
    
    #open SRT file
    srtfile = open(inputfile, "r", encoding="utf-8-sig")

    #parse subs into a generator
    subtitle_generator = srt.parse(srtfile)
    
    message = str()
    styled = False
    
    for i in subtitle_generator:
        if i.content != add_style_codes(i.content):
            styled = True
        if not check_EIA608_encoding(i.content):
            fixed = fix_encoding(bytes(i.content, 'utf-8')) + b"\n"
            if not check_EIA608_encoding(str(fixed, 'utf-8')):
                message += f"Line: {i.index}\n"
                message += str(fixed) + "\n"
                
        if '{' in i.content:
            message += f"Line: {i.index} may have additional text style formatting\n"
            message += str(fixed) + "\n"
            
        if not check_caption_length(i.content):
            message += f"Line: {i.index} is too long\n"
        
    if not message:
        message = "No encoding problems\n"

    if styled:
        message = message + "Lines in this file are styled (italicized or underlined)"
        
    print(message)
    srtfile.close()
