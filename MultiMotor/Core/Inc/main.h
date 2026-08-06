#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32c0xx_ll_rcc.h"
#include "stm32c0xx_ll_bus.h"
#include "stm32c0xx_ll_system.h"
#include "stm32c0xx_ll_exti.h"
#include "stm32c0xx_ll_cortex.h"
#include "stm32c0xx_ll_utils.h"
#include "stm32c0xx_ll_pwr.h"
#include "stm32c0xx_ll_usart.h"
#include "stm32c0xx_ll_gpio.h"
#include "stm32c0xx_ll_tim.h"

#define LED_GREEN_PIN       LL_GPIO_PIN_5
#define LED_GREEN_PORT      GPIOA
#define LED_BLUE_PIN        LL_GPIO_PIN_9
#define LED_BLUE_PORT       GPIOC
#define BUTTON_PIN          LL_GPIO_PIN_13
#define BUTTON_PORT         GPIOC

/* 6 motors — timer, channel, pin, port, AF */
typedef struct {
    TIM_TypeDef *tim;
    uint32_t channel;       /* LL_TIM_CHANNEL_CHx */
    uint32_t pin;
    GPIO_TypeDef *port;
    uint32_t af;
} MotorConfig;

extern const MotorConfig motors[6];

void Error_Handler(void);

#ifdef __cplusplus
}
#endif
#endif
