import oscP5.*;
import netP5.*;

OscP5 oscP5;
NetAddress myLocation;

boolean messageDetailsSent = false;

void setup() {
  size(600, 600);
  colorMode(HSB, 360, 100, 100);
  background(48, 6, 100);
  stroke(217, 4, 56);
  textSize(18);

  noFill();
  oscP5 = new OscP5(this, 12000);
  myLocation = new NetAddress("127.0.0.1", 9000);

  if (messageDetailsSent == false) {
    sendMessageDetails();
    messageDetailsSent = true;
  }
}

void draw() {
  point(0, 0);
}

void sendMessageDetails() {
  OscMessage messageDetails = new OscMessage("/sketch/messages");
  messageDetails.add("/centerx");
  messageDetails.add("f");
  messageDetails.add("center_x");

  oscP5.send(messageDetails, myLocation);
}

void oscEvent(OscMessage message) {
  println("### OSC message received:");
  println("    addrpattern: "+message.addrPattern());
  println("    typetag:"+message.typetag());

  if (message.checkAddrPattern("/complex/a")) {
    if (message.checkTypetag("ff")) {
      print("message received");
    }
  }
}
