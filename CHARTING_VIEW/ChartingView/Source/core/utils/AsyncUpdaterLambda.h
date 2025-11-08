/*
  ==============================================================================

	AsyncUpdaterLambda.h
	Created: 8 Nov 2025 12:03:09am
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "JuceHeader.h"

class AsyncUpdaterLambda : public AsyncUpdater {
public:

	std::function<void()> onAsyncUpdate;

	AsyncUpdaterLambda() {

	}

	AsyncUpdaterLambda(std::function<void()> onAsyncUpdate) : onAsyncUpdate(onAsyncUpdate) {

	}


	void handleAsyncUpdate() override {
		if (onAsyncUpdate)
			onAsyncUpdate();
	}

};

