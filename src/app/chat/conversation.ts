import { Agent } from '../data/interfaces/agent';
import { ConversationData, ConversationVariable } from '../data/interfaces/conversation';
import { Message } from '../data/interfaces/message';
import { BehaviorSubject, Observable } from 'rxjs';


export class Conversation implements ConversationData {
  // Variables inherited from the ConversationData interface
  id: number;
  messagesPartOfSummary: number;
  enviorementVariables: ConversationVariable[];
  summary: string;
  participants: string[];

  // The conversation is responsible for managing the messages array.
  private messagesSubject: BehaviorSubject<Message[]>;
  public messagesObservable: Observable<Message[]>;

  // Constructor
  constructor(id: number, messages: Message[], messagesPartOfSummary: number, 
    enviorementVariables: ConversationVariable[], summary: string, participants: string[]) {
      // Initialize the conversation variables
      this.id = id;
      this.messagesPartOfSummary = messagesPartOfSummary;
      this.enviorementVariables = enviorementVariables;
      this.summary = summary;
      this.participants = participants;

      // Initialize the messages array and expose it as an observable.
      this.messagesSubject = new BehaviorSubject<Message[]>(messages.sort((a, b) => a.time!.getTime() - b.time!.getTime())); 
      this.messagesObservable = this.messagesSubject.asObservable();
  }

  // Get those messages that are not part of the conversation summary
  private getNonSummarizedMessages(messages: Message[]) {
    // Start slicing from the index after the last summarized message
    return messages.slice(this.messagesPartOfSummary).map((message: Message) => {
      return {role: message.role, content: message.content};
    });
  }

  // Convert a conversation to an array of messages used by the openai API
  private getAsMessages(){
    // Prepare the messages array
    const messages: Message[] = [];

    // Add the enviorement variables to the messages
    if (this.enviorementVariables.length > 0) {
      // Prepare the enviorement variables
      var envVarStr: string = 'A list of environment variables up to this point:\n';
      for(let i = 0; i < this.enviorementVariables.length; i++) {
        envVarStr += `${this.enviorementVariables[i].name}: ${this.enviorementVariables[i].value}\n`;
      };
      
      // Add the concatinated enviorement variables to the messages
      messages.push({role: "system", content: envVarStr});
    }

    // Add the summary to the messages
    if (this.summary !== '') {
      messages.push({role: "system", content: `Summary of the conversation up to this point: ${this.summary}\n 
      Keep in mind that the last 4 messages will always be provided even if they are part of the summary.`});
    }

    // Add the participants to the messages
    if (this.participants.length > 0) {
      messages.push({role: "system", content: `A list of the characters participating in the conversation or scenario: ${this.participants}`});
    }
    return messages;
  }

  // Add one or more messages to the conversation
  public addMessage(message: Message | Message[]) {
    if (Array.isArray(message)) {
      // Sort the messages by time
      message.sort((a, b) => a.time!.getTime() - b.time!.getTime());

      // Add the messages to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), ...message]);
    } else {
      // Add the message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), message]);
    }
  }

  // Generate a new message
  public getMessagePrompt(agentPrompt: string): Message[] {
    console.log("Preparing to generate a message...");
    var conversationPromt = this.getAsMessages()
    var generationMessages: Message[] = [
      {role: "system", content: agentPrompt}];
    const messagesNotInSummary = this.getNonSummarizedMessages(this.messagesSubject.getValue());

    if (messagesNotInSummary.length < 4) {
      // Get the last 4 messages
      generationMessages = generationMessages.concat(
        conversationPromt.concat(
          this.messagesSubject.getValue().slice(-4).map((message: Message) => {
            return {role: message.role, content: message.content};
          })));
    } else {
      // Combine the messages
      generationMessages = generationMessages.concat(conversationPromt.concat(messagesNotInSummary));
    }
    return generationMessages;
  }

  // Method to extract data conforming to ConversationData for storage
  public toConversationData(): ConversationData {
    return {
      id: this.id,
      messagesPartOfSummary: this.messagesPartOfSummary,
      enviorementVariables: this.enviorementVariables,
      summary: this.summary,
      participants: this.participants,
    };
  }

  // Method to check if and update the conversation summary
  public async updateSummary(prompt: string, summaryApi: any){
    const currentMessages = this.messagesSubject.getValue();
    const messagesNotInSummary = this.getNonSummarizedMessages(currentMessages);

    // Log the current state of the conversation
    console.log({
      totalMessages: currentMessages.length, 
      messagesInSummary: this.messagesPartOfSummary, 
      messagesNotInSummary: messagesNotInSummary.length,
    });

    // Check if the JSON string is long enough to be summarized
    if (JSON.stringify(messagesNotInSummary).length > 10240 && currentMessages.length - this.messagesPartOfSummary > 4) {
      console.log('Summarizing the conversation...');

      // Create a summary package to be sent to the API
      var summaryPackage = [{role: "system", content: prompt}];

      // Add the messages that are not part of the conversation summary to the summary package
      summaryPackage = summaryPackage.concat(messagesNotInSummary.concat([
        {role: "system", content: `Your task now is to generate a summary of the ongoing conversation. 
        This involves periodically updating the summary to include new information while ensuring the coherence and accuracy of the overall context. 
        When updating, carefully integrate new details into the existing summary without omitting crucial elements or introducing inaccuracies. 
        Maintain the essence of the conversation, focusing on key points, decisions, and insights. \n
        Current summary: [${this.summary}].\n Please update this summary by incorporating the most recent exchanges, highlighting any new developments or conclusions. 
        Ensure the updated summary remains clear and succinct.`}
      ]));

      // Generate a summary
      await summaryApi.chatComplete(summaryPackage).then((response: any) => {
        // Update the conversation summary
        this.summary = response.choices[0].message.content;
        // Update the number of messages that are part of the summary
        this.messagesPartOfSummary = currentMessages.length;
        console.log("Conversation summary updated!");
      });
    }
  }

  // Get conversation promt
  private updateConversationPromt() {
    // Prepare the enviorement variables
    var envVarStr: string = '';
    for(let i = 0; i < this.enviorementVariables.length; i++) {
      envVarStr += `${this.enviorementVariables[i].name}: ${this.enviorementVariables[i].value}\n`;
    };
    
    // Assemble the conversation promt
    var promt: string = 
    `The following data is about the course of the conversation. To stay within the context window and provide some additional information to keep the conversation consistent, the conversation will be summarized and only the last few messages will be provided. Keep in mind that these may or may not be part of the following conversation summery or variables. If any of the values are empty they have not been set yet.\n\n
    A list of the characters participating in the conversation or scenario:
    ${this.participants}\n\n
    A list of environment variables up to this point:
    ${envVarStr}\n\n
    Summary of the conversation up to this point:
    ${this.summary}\n\n
    The last 10 messages exchanged by the participants:\n`;
    return promt;
  }

  // Update the conversation
  public updateConversation(
    summary: string, 
    messagesPartOfSummary: number, 
    enviorementVariables: ConversationVariable[], 
    participants: string[]) {
    // Update the summary and recent messages
    this.updateSummary(summary, messagesPartOfSummary);

    // Update the enviorement variables and participants
    this.enviorementVariables = enviorementVariables;
    this.participants = participants;
  }
}
