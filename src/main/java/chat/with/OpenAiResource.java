package chat.with;

import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;


@Path("/openai")
public class OpenAiResource {

    @POST
    @Path("/chat")
    @Produces(MediaType.APPLICATION_JSON)
    public Response generateChatCompletion(/* Your request payload here */) {
    Client client = ClientBuilder.newClient();
    String openAiUrl = "https://api.openai.com/v1/chat/completions";
    String apiKey = "your_api_key_here"; // Securely store and retrieve your API key

    String requestBody = /* Convert your request payload to JSON string */;

    Response response = client.target(openAiUrl)
        .request(MediaType.APPLICATION_JSON)
        .header("Authorization", "Bearer " + apiKey)
        .post(Entity.entity(requestBody, MediaType.APPLICATION_JSON));

    // Handle the response
    String responseBody = response.readEntity(String.class);
    return Response.status(response.getStatus())
                   .entity(responseBody)
                   .build();
    }
}
