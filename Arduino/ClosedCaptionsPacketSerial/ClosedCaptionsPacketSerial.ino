#include <TVout.h>
#include <PacketSerial.h>
#include <AceCRC.h>

using namespace ace_crc::crc16ccitt_nibblem;

#define W 120
#define H  96

TVout TV;

uint8_t closedCaption[100];
size_t ccLength = 0;

//This is for debugging because this program uses nearly all ram 
//during runtime, and freeMemory returns amount of free memory
#ifdef __arm__
// should use uinstd.h to define sbrk but Due causes a conflict
extern "C" char* sbrk(int incr);
#else  // __ARM__
extern char *__brkval;
#endif  // __arm__

int freeMemory() {
  char top;
#ifdef __arm__
  return &top - reinterpret_cast<char*>(sbrk(0));
#elif defined(CORE_TEENSY) || (ARDUINO > 103 && ARDUINO != 151)
  return &top - __brkval;
#else  // __arm__
  return __brkval ? &top - __brkval : &top - __malloc_heap_start;
#endif  // __arm__
}

void setup() {
  Serial.begin(19200);
  Serial.println(TV.begin(NTSC,W,H), DEC);
  
  initOverlay();
  TV.disableScreenRender();

  //If you wire even/odd into pin 3 of the arduino you can choose
  //the field (even or odd) that the closed caption signal is transmitted on
  //In EIA-608 the CC1 signal is transmitted on only the odd fields
  //uncomment the following line to use this feature
  //TV.setCCField(ODD);

  //Enable builtin LED
  DDRB |= _BV(PB5);
  PORTB &= ~_BV(PB5);
  
  TV.delay_frame(50);
  
  //Erase displayed memory (EDM)
  TV.printCC(0x14, 0x2C);
  TV.printCC(0x14, 0x2C);

  //Erase non displayed memory (ENM)
  TV.printCC(0x14, 0x2E);
  TV.printCC(0x14, 0x2E);
}

void loop() {
  PacketSerial myPacketSerial;
  
  myPacketSerial.setStream(&Serial);
  myPacketSerial.setPacketHandler(&onPacketReceived);
  
  Serial.print('b');
  
  char firstByte, secondByte = 0;
  for(;;)
  {
    //The shortest possible closed caption should
    //be 2 bytes (the display caption control code)
    if(ccLength >= 2)
    {
      Serial.end();

      if(!((closedCaption[0] == 0x14) && (closedCaption[1] == 0x2C)))
      {
        //Erase non displayed memory (ENM)
        TV.printCC(0x14, 0x2E);
        TV.printCC(0x14, 0x2E);

        //Start pop-on captions (RCL)
        TV.printCC(0x14, 0x20);
        TV.printCC(0x14, 0x20);
      }

      for(uint8_t i = 0; i < ccLength; i++)
      {
        firstByte = 0;
        secondByte = 0;

        firstByte = closedCaption[i];
    
        if((i + 1) < (ccLength))
        {
          i++;
          secondByte = closedCaption[i];
        }
        
        //control codes must always be sent as a pair so
        //we gotta check if the secondByte is the first
        //byte of a control code pair which always fall
        //between 0x11 and 0x17   
        if((secondByte >= 0x11) && (secondByte <= 0x17))
        {
          TV.printCC(firstByte, 0);
          if((i + 1) < (ccLength))
          {
            i++;
            TV.printCC(secondByte, closedCaption[i]);
          }
        }
        else
        {
          TV.printCC(firstByte, secondByte);
        }
        
        //Uncomment for debugging
        //TV.print(firstByte);
        //TV.print(secondByte);
      }
      
      ccLength = 0;
      Serial.begin(19200);
      while(!Serial);
      Serial.write('\r');
    }
    else
    {
      // Call update to receive, decode and process incoming packets.
      blinky();
      myPacketSerial.update();  
    }
  } 
}

void blinky()
{
  static uint16_t counter=0;
  if(counter >= 30000)
  {
    //Serial.println(freeMemory());
    PORTB ^= _BV(PB5);
    counter=0;
  }
  counter++;
}


// Initialize ATMega registers for video overlay capability.
// Must be called after tv.begin().
void initOverlay() {
  TCCR1A = 0;
  // Enable timer1.  ICES0 is set to 0 for falling edge detection on input capture pin.
  TCCR1B = _BV(CS10);

  // Enable input capture interrupt
  TIMSK1 |= _BV(ICIE1);

  // Enable external interrupt INT0 on pin 2 with falling edge.
  EIMSK = _BV(INT0);
  EICRA = _BV(ISC01);
}

// Required to reset the scan line when the vertical sync occurs
ISR(INT0_vect) {
  display.scanLine = 0;
}

void onPacketReceived(const uint8_t* buffer, size_t size)
{
  if(size == 0)
  {
    Serial.write('\a');
    return;
  }
  
  
  crc_t const crcCheck = crc_calculate(buffer, size-2);
  
  crc_t const crcReceived = ((buffer[size - 2] << 8) & 0xFF00) + (buffer[size - 1] & 0x00FF);
  
  if(crcCheck != crcReceived)
  {
    Serial.write('\a');
  }
  else
  {
    //only print back the data without checksum
    for(uint8_t i = 0; i < size-2; i++)
    {
      closedCaption[i] = buffer[i];
 
      //Serial.write(buffer[i]);
    }
    //send the size minus the CRC bytes
    ccLength = size - 2;
  }
}
