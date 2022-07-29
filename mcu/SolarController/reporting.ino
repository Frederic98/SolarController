void reportTemperature(uint8_t index, float value){
  // printf %f doesn't work - so use dtostrf instead, with the text buffer + offset of sprintf
  dtostrf(value, 0, 2, serialTxBuffer+sprintf(serialTxBuffer, "T:%u=", index));
  Serial.println(serialTxBuffer);
}

void reportTemperatureInfo(uint8_t index){
  // Probe state
  printf("TSTATE:%u=%u\n", index, sensorStatus[index]);

  // If probe disconnected, nothing else to report
  if(sensorStatus[index] == 0) return;
  
  // Probe ID
  printf("TID:%u=", index);
  for(int j=0;j<8;j++){
    printf("%02X", sensorID[index][j]);
  }
  Serial.println();
}

void reportRelay(uint8_t index){
  if(index >= relayCount) return;
  printf("R:%u=%u\n", index, (digitalRead(relays[index]) == HIGH) ? 1 : 0);
}

void reportOutput(uint8_t index){
  if(index >= digitalOutCount) return;
  printf("O:%u=%u\n", index, (digitalRead(digitalOut[index]) == HIGH) ? 1 : 0);
}

void reportInput(uint8_t index){
  if(index >= digitalInCount) return;
  printf("I:%u=%u\n", index, (digitalInStates[index] == HIGH) ? 1 : 0);
}

void reportAnalog(uint8_t index){
  float value;
  if(index < analogInCount){
    value = analogInStates[index];
    dtostrf(value, 0, 2, serialTxBuffer+sprintf(serialTxBuffer, "A:%u=", index));
  }else{
    value = analogInRef;
    dtostrf(value, 0, 2, serialTxBuffer+sprintf(serialTxBuffer, "AREF:1100="));
  }
  Serial.println(serialTxBuffer);
}

void reportPWM(uint8_t index){
  if(index >= analogOutCount) return;
  float value = analogOutStates[index];
  dtostrf(value, 0, 2, serialTxBuffer+sprintf(serialTxBuffer, "P:%u=", index));
  Serial.println(serialTxBuffer);
}
