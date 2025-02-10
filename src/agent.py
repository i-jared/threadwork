
class Agent:
    def __init__(self, request: function, prompt: str, depth: int):
        self.request = request
        self.prompt = prompt
        self.depth = depth
    
    def run(self):
        return self.request(self.prompt)


class ChooseTechAgent(Agent):
    def __init__(self, request: function, input: str, depth: int):
        prompt = f"""Choose the best technologies for the given app description.
        be exhaustive but concise. give your output in a list in the format:
        ```
        - <tech1>: <use case>
        - <tech2>: <use case>
        - <tech3>: <use case>
        ```
        and so on.
        
        input: {input}
        """
        super().__init__(request, prompt, depth)

    def run(self):
        return self.request(self.prompt)

class DetailUpAgent(Agent):
    def __init__(self, request: function, input: str, depth: int):
        prompt = f"""Given this app, app feature, or app component, 
        increase the detail of the description. 
        input: {input}
        """
        super().__init__(request, prompt, depth)

    def run(self):
        return self.request(self.prompt)

class WriteCodeAgent(Agent):
    def __init__(self, request: function, input: str, depth: int, filepath: str):
        prompt = f"""Given this app, app feature, or app component, 
        write the code for it. exclude any comments or other non-code text.
        
        input: {input}
        """
        super().__init__(request, prompt, depth)

    def run(self):
        code = self.request(self.prompt)
        # TODO: write code to file