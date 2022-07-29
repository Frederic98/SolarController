#include <avr/wdt.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define printf(fmt, ...) snprintf(serialTxBuffer, serialTxSize, fmt, ##__VA_ARGS__); Serial.print(serialTxBuffer)
#define serialTxSize 64
char serialTxBuffer[serialTxSize];

// Pin definitions
OneWire onewireBus[] = { A0, A1, A2, A3, A5, A4, 13, 12 };
uint8_t relays[] = {2,3,4,5,6,7};
uint8_t digitalIn[] = {8,10};
uint8_t digitalOut[] = {};
uint8_t analogIn[] = {6, 7};    // A6, A7
uint8_t analogOut[] = {9,11};

const int oneWireCount = sizeof(onewireBus)/sizeof(OneWire);
const int relayCount = sizeof(relays)/sizeof(relays[0]);
const int digitalInCount = sizeof(digitalIn)/sizeof(digitalIn[0]);
const int digitalOutCount = sizeof(digitalOut)/sizeof(digitalOut[0]);
const int analogInCount = sizeof(analogIn)/sizeof(analogIn[0]);
const int analogOutCount = sizeof(analogOut)/sizeof(analogOut[0]);

DallasTemperature sensors[oneWireCount];
DeviceAddress sensorID[oneWireCount];
float temperatures[oneWireCount];
uint8_t sensorStatus[oneWireCount];
bool digitalInStates[digitalInCount];
bool digitalOutStates[digitalOutCount];
float analogInStates[analogInCount];
float analogInRef;
float analogOutStates[analogOutCount];


uint32_t loopCounter = 0;
uint32_t lastWDTReset = 0;
uint32_t lastTempUpdate = 0;
uint32_t digitalInReportTime[digitalInCount];

char serialRecvBuffer[64];
uint8_t serialRecvIndex = 0;

#define ADC_THROWAWAY_COUNT 5
uint8_t adcChannel = 0;
uint8_t adcThrowaway = ADC_THROWAWAY_COUNT;

void processCommand(char* txt);
void pollTemperatures();

void setup() {
  wdt_disable();
  wdt_reset();
  wdt_enable(WDTO_4S);
  
  Serial.begin(9600);
  printf("B:0=%u\n", MCUSR&0x0F);
  MCUSR &= 0xF0;
  for (int i = 0; i < oneWireCount; i++) {
    sensors[i].setOneWire(&onewireBus[i]);
    sensors[i].begin();
    sensorStatus[i] = 0;
//    reportTemperature(i, 0);
  }
  for(int i=0; i<relayCount; i++){
    pinMode(relays[i], OUTPUT);
    digitalWrite(relays[i], LOW);
  }
  for(int i=0; i<analogOutCount; i++){
    pinMode(analogOut[i], OUTPUT);
    setPWM(i, 0);
  }
  for(int i=0; i<digitalOutCount; i++){
    pinMode(digitalOut[i], OUTPUT);
    digitalWrite(digitalOut[i], LOW);
  }
  for(int i=0; i<digitalInCount; i++){
    pinMode(digitalIn[i], INPUT_PULLUP);
  }
  // Analog IN
  ADMUX = (1 << REFS0);
  ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);
  setADCChannel(0);
}

void loop() {
  unsigned long currentMillis = millis();
  if (currentMillis - lastTempUpdate >= 500) {
    wdt_reset();
  }
  while(Serial.available()){
    char txt = Serial.read();
    if(txt == '\n'){
      serialRecvBuffer[serialRecvIndex] = '\0';
      processCommand(serialRecvBuffer);
      serialRecvIndex = 0;
    }else if(txt == '\r'){
      // Ignore \r chars
    }else{
      serialRecvBuffer[serialRecvIndex++] = txt;
    }
  }

  // Once per second, report continuous (analog) values (temperature, analogIn)
  if (currentMillis - lastTempUpdate >= 1000) {
    lastTempUpdate = currentMillis;
    
    // Read temperatures from probes
    pollTemperatures();

    // Initiate new measurement
    for (int i = 0; i < oneWireCount; i++) {
      sensors[i].requestTemperatures();
    }

    // Also report ADC channels
    for (int i=0; i<=analogInCount; i++) {
      // i<=analogInCount - last is for AREF
      reportAnalog(i);
    }
  }

  if(!(ADCSRA & (1<<ADSC))){
    if(!adcThrowaway){
      if(adcChannel < analogInCount){
        analogInStates[adcChannel] = ADC / 10.23;
        adcChannel++;
      }else{
        analogInRef = ADC / 10.23;
        adcChannel = 0;
      }
      setADCChannel(adcChannel);
      adcThrowaway = ADC_THROWAWAY_COUNT;
    }else{
      adcThrowaway--;
    }
    startADC();
  }
  for(int i=0; i<digitalInCount; i++){
    bool state = digitalRead(digitalIn[i]);
    if(state != digitalInStates[i] && currentMillis - digitalInReportTime[i] > 100){
      digitalInReportTime[i] = currentMillis;
      digitalInStates[i] = state;
      reportInput(i);
    }
  }
  
  loopCounter++;
}

char* splitstr(char* txt, char seperator){
  // Replace seperator by a null character, and return a pointer to the next char
  if(txt == NULL) return NULL;
  char* split = strchr(txt, seperator);
  if(split == NULL) return NULL;
  *split = '\0';
  return split + 1;
}

int stoi(char* txt, char** idx){
  int result = atoi(txt);
  char character;
  for(unsigned int pos = 0;;pos++){
    character = *(txt + pos);
    if(character >= '0' && character <= '9') continue;
    if(pos == 0 && (character == '-' || character == '+')) continue;
    *idx = txt + pos;
    break;
  }
  return result;
}



void processCommand(char* txt){
  // Extract info from the string in the form of field:idx=value
  char* field = txt;
  if(strchr(field, '=') != NULL){
    // If equals sign in string, it's a SET command
    char* idx = splitstr(field, ':');
    if(idx == NULL) return;
    char* val = splitstr(idx, '=');
    if(val == NULL) return;

    int index = stoi(idx, &idx);    // Convert idx_str to a number, then set idx_str to (hopefully) the following null character
    if(*idx != '\0') return;            // If the character after any numeric chars is not the terminating null char, ignore message
      
    if(strcmp(field, "R") == 0){
      int value = stoi(val, &val);
      if(*val != '\0') return;
      setRelay(index, value);
    }else if(strcmp(field, "P") == 0){
      float value = strtod(val, &val);
      if(*val != '\0') return;
      setPWM(index, value);
    }else if(strcmp(field, "O") == 0){
      int value = stoi(val, &val);
      if(*val != '\0') return;
      setOutput(index, value);
    }
  }else if(strchr(field, '?') != NULL){
    // If question mark in string, it's a GET command
    bool indexPresent = false;
    int index;
    char* idx = splitstr(field, ':');
    char* end;
    if(idx != NULL){
      end = splitstr(idx, '?');
      indexPresent = true;
      index = stoi(idx, &idx);            // Convert idx_str to a number, then set idx_str to (hopefully) the following null character
      if(*idx != '\0') return;            // If the character after any numeric chars is not the terminating null char, ignore message
    }else{
      end = splitstr(field, '?');
    }
    if(end == NULL || *end != '\0') return;

    if(strcmp(field, "T") == 0){
      if(indexPresent) reportTemperatureInfo(index);
      else{
        for(index=0; index<oneWireCount; index++){
          reportTemperatureInfo(index);
        }
      }
    }else if(strcmp(field, "R") == 0){
      if(indexPresent) reportRelay(index);
      else{
        for(index=0; index<relayCount; index++){
          reportRelay(index);
        }
      }
    }else if(strcmp(field, "P") == 0){
      if(indexPresent) reportPWM(index);
      else{
        for(index=0; index<analogOutCount; index++){
          reportPWM(index);
        }
      }
    }else if(strcmp(field, "O") == 0){
      if(indexPresent) reportOutput(index);
      else{
        for(index=0; index<digitalOutCount; index++){
          reportOutput(index);
        }
      }
    }else if(strcmp(field, "I") == 0){
      if(indexPresent) reportInput(index);
      else{
        for(index=0; index<digitalInCount; index++){
          reportInput(index);
        }
      }
    }
  }
}

void setRelay(uint8_t idx, bool value){
  if(idx >= relayCount) return;
  digitalWrite(relays[idx], value);
  reportRelay(idx);
//  Serial.println(serialBuffer);
}

void setOutput(uint8_t idx, bool value){
  if(idx >= digitalOutCount) return;
  digitalWrite(digitalOut[idx], value);
}

void setPWM(uint8_t idx, float value){
  if(idx >= analogOutCount) return;
  if(value < 0) value = 0;
  if(value > 100) value = 100;
  int dutycycle = value * 2.55;
  dutycycle = constrain(dutycycle, 0, 255);
  analogWrite(analogOut[idx], dutycycle);
  analogOutStates[idx] = value;
  reportPWM(idx);
}

void setADCChannel(uint8_t index){
  // Set ADC channel according to analogIn[index], clear interrupt flag and start a conversion
//  printf("Switch to AI%u (ADC%u)\n", index, analogIn[index]);
  ADMUX &= ~0x0F;
  if(index < analogInCount){
    ADMUX |= analogIn[index] & 0x0F;
  }else{
    ADMUX |= 0b1110;    // 1.1 VREF
  }
  
//  Serial.print("ADMUX=");
//  Serial.println(ADMUX, HEX);
}

void startADC(){
  ADCSRA |= (1<<ADSC) | (1<<ADIF);
}

void pollTemperatures(){
  for (int i = 0; i < oneWireCount; i++) {
    switch(sensorStatus[i]){
      case 0:
        // Sensor was disconnected, check for new sensors
        onewireBus[i].reset();
        sensors[i].begin();
        if(sensors[i].getAddress(sensorID[i], 0)){
          // New sensor found!
          sensorStatus[i] = 1;
          sensors[i].setResolution(12);
          reportTemperatureInfo(i);
        }
        break;
      case 1:
        // Sensor was found, but not initialized
        // Ignore this temperature measurement for now...
        sensors[i].getTempC(sensorID[i]);
        sensorStatus[i] = 2;
        reportTemperatureInfo(i);
        break;
      case 2:
        // Normal sensor status - all OK
        temperatures[i] = sensors[i].getTempC(sensorID[i]);
        if(temperatures[i] == DEVICE_DISCONNECTED_C){
          sensorStatus[i] = 0;
          reportTemperatureInfo(i);
        }else{
          reportTemperature(i, temperatures[i]);
        }
    }
  }
}
